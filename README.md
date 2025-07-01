# Water Polo Rankings API - Serverless

This is the serverless version of the Water Polo Rankings API, designed to be deployed on Vercel.

## Structure

```
serverless/
├── api/
│   ├── index.py                    # Main Flask application
│   ├── mens_waterpolo_rankings.json
│   └── womens_waterpolo_rankings.json
├── requirements.txt                # Python dependencies
├── vercel.json                    # Vercel configuration
├── .vercelignore                  # Files to ignore during deployment
└── README.md                      # This file
```

## Deployment to Vercel

1. **Install Vercel CLI** (if not already installed):
   ```bash
   npm install -g vercel
   ```

2. **Set up environment variables** in Vercel:
   - `MONGO_URI`: Your MongoDB connection string

3. **Deploy**:
   ```bash
   cd serverless
   vercel
   ```

4. **Set environment variables** (if not done through the dashboard):
   ```bash
   vercel env add MONGO_URI
   ```

## Environment Variables

- `MONGO_URI`: MongoDB connection string (required)

## API Endpoints

### Men's Water Polo (MWP)
- `GET /api/MWP/matrix` - Get the probability matrix data
- `GET /api/MWP/matches/<row_rank>/<col_rank>` - Get matches between specific ranks
- `GET /MWP/rankings/<team_names>/<start_date>/<end_date>` - Get team ranking history

### Women's Water Polo (WWP)
- `GET /api/WWP/matrix` - Get the probability matrix data
- `GET /api/WWP/matches/<row_rank>/<col_rank>` - Get matches between specific ranks
- `GET /WWP/rankings/<team_names>/<start_date>/<end_date>` - Get team ranking history

### Utility
- `GET /api/health` - Health check
- `GET /api/cache/info` - Cache statistics
- `POST /api/cache/clear` - Clear cache

## Local Development

To run locally:

```bash
cd serverless
pip install -r requirements.txt
export MONGO_URI="your_mongodb_connection_string"
python api/index.py
```

The server will run on `http://localhost:5001`.

## Notes

- The app includes caching to improve performance
- CORS is enabled for all origins (consider restricting in production)
- Cache TTL is set to 1 hour
- Maximum cache size is 100 items
