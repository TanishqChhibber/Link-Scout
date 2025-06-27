# LinkScout

LinkScout is a LinkedIn lead finder and search tool with persistent search history, Excel export, and a user-friendly web interface.

## Features
- Search LinkedIn profiles by role or custom keyword
- Prioritize Indian profiles, then fill with global results
- Persistent search history (even after server restart)
- Download all results as Excel or CSV
- Google Sheets export
- Open all LinkedIn profiles in browser (server-side)
- Docker and Docker Compose support for easy deployment

## Quick Start (Local)
1. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
2. **Run the app:**
   ```sh
   uvicorn main:app --reload
   ```
3. **Open in browser:**
   - Go to [http://localhost:8000](http://localhost:8000)

## Docker Usage
1. **Build and run with Docker Compose:**
   ```sh
   docker-compose up --build
   ```
2. **Access the app:**
   - [http://localhost:8000](http://localhost:8000)

## Project Structure
- `main.py` — FastAPI backend
- `static/index.html` — Main frontend
- `static/history.json` — Persistent search history
- `requirements.txt` — Python dependencies
- `Dockerfile`, `docker-compose.yaml` — Containerization

## Environment Variables
- Set your Serper.dev API key as an environment variable:
  ```sh
  export SERPER_API_KEY=your_actual_key_here
  ```
- (Optional) For Docker, add to docker-compose.yaml:
    ```yaml
    environment:
      - SERPER_API_KEY=your_actual_key_here
    ```
- Never commit your API keys to version control!

## Contributing
Pull requests are welcome!
