import os
import sys
from flask import Flask, jsonify, make_response
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import json
import csv
from datetime import datetime
import time
import hashlib

app = Flask(__name__)
CORS(app)  # allow all origins by default; in production, restrict to YOUR Vercel domain

# Cache configuration
CACHE = {}
CACHE_TTL = 3600  # 1 hour in seconds
CACHE_MAX_SIZE = 100  # Maximum number of cached items

# 1) Configure your MongoDB URI (local or Atlas).
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI, server_api=ServerApi('1'))
client.admin.command('ping')
db = client.get_database(name="WPTable")
WWP_db = client.get_database(name="WWP")

# 2) Collections
win_col = db["wins"]
prob_col = db['Probabilities']
delim_col = db["Delim"]
matches_col = db["matches"]  # Add matches collection

wwp_win_col = WWP_db["wins"]
wwp_prob_col = WWP_db['Probabilities']
wwp_delim_col = WWP_db["Delim"]
wwp_matches_col = WWP_db["matches"] 

print(f"Win documents: {win_col.count_documents({})}")
print(f"Delim documents: {delim_col.count_documents({})}")
print(f"Matches documents: {matches_col.count_documents({})}")

# 3) We know exactly which ranks exist and in which order.
RANK_ORDER = [str(i) for i in range(1, 21)] + ["unranked"] 
WWP_RANK_ORDER = [str(i) for i in range(1, 26)] + ["unranked"]

# Load rankings data from files in the same directory
current_dir = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(current_dir, "mens_waterpolo_rankings.json"), "r", encoding="utf-8") as f:
    rankings = json.load(f)

with open(os.path.join(current_dir, "womens_waterpolo_rankings.json"), "r", encoding="utf-8") as f:
    wwp_rankings = json.load(f)

# Cache management functions
def cache_key_generator(*args):
    """Generate a cache key from arguments"""
    key_string = "_".join(str(arg) for arg in args)
    return hashlib.md5(key_string.encode()).hexdigest()

def get_from_cache(key):
    """Get data from cache if it exists and is not expired"""
    if key in CACHE:
        data, timestamp = CACHE[key]
        if time.time() - timestamp < CACHE_TTL:
            return data
        else:
            # Remove expired entry
            del CACHE[key]
    return None

def set_cache(key, data):
    """Set data in cache with timestamp"""
    # Implement simple LRU by removing oldest entries if cache is full
    if len(CACHE) >= CACHE_MAX_SIZE:
        # Remove the oldest entry
        oldest_key = min(CACHE.keys(), key=lambda k: CACHE[k][1])
        del CACHE[oldest_key]
    
    CACHE[key] = (data, time.time())

def add_cache_headers(response, max_age=3600):
    """Add cache headers to response"""
    response.headers['Cache-Control'] = f'public, max-age={max_age}, s-maxage={max_age}, stale-while-revalidate=7200'
    response.headers['ETag'] = hashlib.md5(response.get_data()).hexdigest()
    return response


@app.route("/api/MWP/matrix", methods=["GET"])
def get_matrix():
    try:
        # Check cache first
        cache_key = cache_key_generator("matrix", "v1")
        cached_data = get_from_cache(cache_key)
        
        if cached_data:
            print("Serving matrix data from cache")
            response = make_response(jsonify(cached_data))
            return add_cache_headers(response), 200
        
        print("Fetching matrix data from database")
        delim_data = list(delim_col.find({}, {"_id": 0}))# Game counts
        prob_data = list(prob_col.find({}, {"_id": 0}))
        
        headers = RANK_ORDER.copy() # ["1","2",...,"20","unranked"]
        
        result_data = {
            "headers": headers,
            "probData": prob_data, # Changed from "winData" to "probData"
            "delimData": delim_data
        }
        
        # Cache the result
        set_cache(cache_key, result_data)
        
        print(f"Returning {len(prob_data)} probability rows and {len(delim_data)} delim rows")
        response = make_response(jsonify(result_data))
        return add_cache_headers(response), 200
        
    except Exception as e:
        print(f"Error in /api/matrix: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/MWP/matches/<row_rank>/<col_rank>", methods=["GET"])
def get_matches(row_rank, col_rank):
    """Get matches between two specific ranks"""
    try:
        # Check cache first
        cache_key = cache_key_generator("matches", row_rank, col_rank)
        cached_data = get_from_cache(cache_key)
        
        if cached_data:
            print(f"Serving matches data for {row_rank}_{col_rank} from cache")
            response = make_response(jsonify(cached_data))
            return add_cache_headers(response), 200
        
        print(f"Fetching matches data for {row_rank}_{col_rank} from database")
        
        # Create the key for matches lookup
        # Try both directions since matches can be stored as "3_9" or "9_3"
        key1 = f"{int(row_rank)-1}_{int(col_rank)-1}"

        # Look for matches document
        matches_doc = matches_col.find({},{"_id": 0})
        games = list(matches_doc)[0][key1]

        result_data = {
            "matches": games,
            "count": len(games),
            "row_rank": row_rank,
            "col_rank": col_rank
        }
        
        # Cache the result
        set_cache(cache_key, result_data)
        
        response = make_response(jsonify(result_data))
        return add_cache_headers(response), 200
        
    except Exception as e:
        print(f"Error in /api/matches/{row_rank}/{col_rank}: {e}")
        return jsonify({"error": str(e)}), 500
    

@app.route("/MWP/rankings/<team_names>/<start_date>/<end_date>", methods=["GET"])
def get_team_ranking_history(team_names, start_date, end_date):
    try:
        # Check cache first
        cache_key = cache_key_generator("rankings", team_names, start_date, end_date)
        cached_data = get_from_cache(cache_key)
        
        if cached_data:
            print(f"Serving ranking history for {team_names} from cache")
            response = make_response(jsonify(cached_data))
            return add_cache_headers(response), 200
        
        print(f"Fetching ranking history for {team_names} from database")
        
        # Convert string dates to datetime objects for comparison
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Parse team names (comma-separated)
        team_list = [name.strip() for name in team_names.split(',')]
        
        history = []
        for date_str, ranking_list in rankings.items():
            # Parse date string to datetime object
            current_date = datetime.strptime(date_str.split('-')[0], "%m/%d/%Y")
            
            # Check if current_date is within the specified range
            if start_dt <= current_date <= end_dt:
                for team in ranking_list:
                    if team['team_name'] in team_list:
                        history.append({
                            "team_name": team['team_name'],
                            "date": current_date.strftime("%Y-%m-%d"),
                            "rank": team['ranking']
                        })
        
        # Sort by date and team name
        history.sort(key=lambda x: (x['date'], x['team_name']))
        
        result_data = {
            "data": history,
            "count": len(history),
            "teams": team_list,
            "date_range": {
                "start": start_date,
                "end": end_date
            }
        }
        
        # Cache the result
        set_cache(cache_key, result_data)
        
        response = make_response(jsonify(result_data))
        return add_cache_headers(response), 200
        
    except Exception as e:
        print(f"Error in /rankings/{team_names}/{start_date}/{end_date}: {e}")
        return jsonify({"error": str(e)}), 500
    


#WWP calls

@app.route("/api/WWP/matrix", methods=["GET"])
def get_WWP_matrix():
    try:
        # Check cache first
        cache_key = cache_key_generator("WWPmatrix", "v1")
        cached_data = get_from_cache(cache_key)
        
        if cached_data:
            print("Serving matrix data from cache")
            response = make_response(jsonify(cached_data))
            return add_cache_headers(response), 200
        
        print("Fetching matrix data from database")
        delim_data = list(wwp_delim_col.find({}, {"_id": 0})) # Game counts
        prob_data = list(wwp_prob_col.find({}, {"_id": 0}))
        
        headers = WWP_RANK_ORDER.copy() # ["1","2",...,"20","unranked"]
        
        result_data = {
            "headers": headers,
            "probData": prob_data, # Changed from "winData" to "probData"
            "delimData": delim_data
        }
        
        # Cache the result
        set_cache(cache_key, result_data)
        
        print(f"Returning {len(prob_data)} probability rows and {len(delim_data)} delim rows")
        response = make_response(jsonify(result_data))
        return add_cache_headers(response), 200
        
    except Exception as e:
        print(f"Error in /api/matrix: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/WWP/matches/<row_rank>/<col_rank>", methods=["GET"])
def get_WWP_matches(row_rank, col_rank):
    """Get matches between two specific ranks"""
    try:
        # Check cache first
        cache_key = cache_key_generator("WWPmatches", row_rank, col_rank)
        cached_data = get_from_cache(cache_key)
        
        if cached_data:
            print(f"Serving matches data for {row_rank}_{col_rank} from cache")
            response = make_response(jsonify(cached_data))
            return add_cache_headers(response), 200
        
        print(f"Fetching matches data for {row_rank}_{col_rank} from database")
        
        # Create the key for matches lookup
        # Try both directions since matches can be stored as "3_9" or "9_3"
        key1 = f"{int(row_rank)-1}_{int(col_rank)-1}"

        # Look for matches document
        matches_doc = wwp_matches_col.find({},{"_id": 0})
        games = list(matches_doc)[0][key1]

        result_data = {
            "matches": games,
            "count": len(games),
            "row_rank": row_rank,
            "col_rank": col_rank
        }
        
        # Cache the result
        set_cache(cache_key, result_data)
        
        response = make_response(jsonify(result_data))
        return add_cache_headers(response), 200
        
    except Exception as e:
        print(f"Error in /api/matches/{row_rank}/{col_rank}: {e}")
        return jsonify({"error": str(e)}), 500
    

@app.route("/WWP/rankings/<team_names>/<start_date>/<end_date>", methods=["GET"])
def get_WWP_team_ranking_history(team_names, start_date, end_date):
    try:
        # Check cache first
        cache_key = cache_key_generator("WWPankings", team_names, start_date, end_date)
        cached_data = get_from_cache(cache_key)
        
        if cached_data:
            print(f"Serving ranking history for {team_names} from cache")
            response = make_response(jsonify(cached_data))
            return add_cache_headers(response), 200
        
        print(f"Fetching ranking history for {team_names} from database")
        
        # Convert string dates to datetime objects for comparison
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        # Parse team names (comma-separated)
        team_list = [name.strip() for name in team_names.split(',')]
        
        history = []
        for date_str, ranking_list in wwp_rankings.items():
            # Parse date string to datetime object
            current_date = datetime.strptime(date_str.split('-')[0], "%m/%d/%Y")
            
            # Check if current_date is within the specified range
            if start_dt <= current_date <= end_dt:
                for team in ranking_list:
                    if team['team_name'] in team_list:
                        history.append({
                            "team_name": team['team_name'],
                            "date": current_date.strftime("%Y-%m-%d"),
                            "rank": team['ranking']
                        })
        
        # Sort by date and team name
        history.sort(key=lambda x: (x['date'], x['team_name']))
        
        result_data = {
            "data": history,
            "count": len(history),
            "teams": team_list,
            "date_range": {
                "start": start_date,
                "end": end_date
            }
        }
        
        # Cache the result
        set_cache(cache_key, result_data)
        
        response = make_response(jsonify(result_data))
        return add_cache_headers(response), 200
        
    except Exception as e:
        print(f"Error in /rankings/{team_names}/{start_date}/{end_date}: {e}")
        return jsonify({"error": str(e)}), 500


 
@app.route("/api/health", methods=["GET"])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "healthy", "message": "Flask server is running"}), 200

@app.route("/api/cache/info", methods=["GET"])
def cache_info():
    """Get cache statistics"""
    cache_stats = {
        "cache_size": len(CACHE),
        "max_cache_size": CACHE_MAX_SIZE,
        "cache_ttl_seconds": CACHE_TTL,
        "cached_keys": list(CACHE.keys()) if len(CACHE) < 20 else f"{len(CACHE)} keys (too many to list)"
    }
    return jsonify(cache_stats), 200

@app.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    """Clear all cache entries"""
    global CACHE
    old_size = len(CACHE)
    CACHE.clear()
    return jsonify({
        "message": f"Cache cleared successfully. Removed {old_size} entries.",
        "cache_size": len(CACHE)
    }), 200


# Export the app for Vercel
# Vercel expects the Flask app to be available as a module-level variable
app.config['ENV'] = 'production'

# For local development
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
