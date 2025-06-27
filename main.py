from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import io
import os
import pandas as pd # Import pandas for DataFrame operations
import json

from utils import search_profiles, export_to_csv, export_to_excel, export_to_google_sheets, open_links_in_browser
from keywords import KEYWORDS

app = FastAPI(
    title="LinkScout: LinkedIn Lead Finder API",
    description="API for searching LinkedIn profiles and exporting leads."
)

# Mount static files to serve the HTML frontend
app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory storage for profiles (for the current session)
_profiles_cache: List[dict] = []

# Configuration for display and search logic
DISPLAY_LIMIT = 100  # Max number of results to show on the page and export
INDIA_PRIORITY_MIN = 100  # Try to fill with Indian profiles first
                       # We will try to fill DISPLAY_LIMIT with Indian profiles first.

# Ensure INDIA_PRIORITY_MIN doesn't exceed DISPLAY_LIMIT (still good practice)
if INDIA_PRIORITY_MIN > DISPLAY_LIMIT:
    INDIA_PRIORITY_MIN = DISPLAY_LIMIT
    print(f"Warning: INDIA_PRIORITY_MIN was set higher than DISPLAY_LIMIT. Adjusted to {DISPLAY_LIMIT}.")

HISTORY_FILE = "static/history.json"

# Load history from disk at startup
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r") as f:
        try:
            _profiles_cache = json.load(f)
        except Exception:
            _profiles_cache = []
else:
    _profiles_cache = []


class SearchRequest(BaseModel):
    selected_keyword: Optional[str] = None
    custom_keyword: Optional[str] = None
    use_all_keywords: bool = False

class Profile(BaseModel):
    name: str
    role: str
    link: str

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """
    Serves the main HTML page for the LinkScout application.
    """
    return FileResponse("static/index.html")

@app.post("/api/search", response_model=List[Profile])
async def search_linkedin_profiles(request_data: SearchRequest):
    """
    Searches LinkedIn profiles based on keywords and returns the results.
    Automatically exports results to an Excel file on the server.
    Prioritizes Indian profiles to fill DISPLAY_LIMIT as much as possible.
    """
    global _profiles_cache # Declare as global to modify the shared list
    # _profiles_cache.clear()  # REMOVE THIS LINE to accumulate profiles across searches

    search_terms = []

    if request_data.use_all_keywords:
        search_terms = KEYWORDS
    elif request_data.selected_keyword:
        search_terms = [request_data.selected_keyword]
    elif request_data.custom_keyword:
        search_terms = [request_data.custom_keyword]
    else:
        raise HTTPException(status_code=400, detail="Please select or enter a keyword.")

    all_found_profiles_for_display = []
    unique_profiles_for_cache = {profile['link']: profile for profile in _profiles_cache}  # Start with existing cache

    for keyword in search_terms:
        print(f"\n--- Processing keyword: '{keyword}' ---")

        indian_profiles_for_this_keyword = []
        global_profiles_for_this_keyword = []
        current_links_for_dedup = set() # Set to track links already added for this keyword

        # 1. Search for Indian profiles first, attempting to fill DISPLAY_LIMIT
        print(f"Attempting to find up to {DISPLAY_LIMIT} Indian profiles for '{keyword}' by requesting a larger pool...")
        indian_results_raw = search_profiles(keyword, location='in', num_results=DISPLAY_LIMIT * 2)  # Request twice the display limit

        if indian_results_raw:
            for profile in indian_results_raw:
                if len(indian_profiles_for_this_keyword) >= DISPLAY_LIMIT:
                    break  # Stop if we've already collected enough Indian profiles for the limit
                if profile['link'] not in current_links_for_dedup:
                    indian_profiles_for_this_keyword.append(profile)
                    current_links_for_dedup.add(profile['link'])
            print(f"Found {len(indian_profiles_for_this_keyword)} unique Indian profiles for '{keyword}'.")

        # 2. If not enough profiles (less than DISPLAY_LIMIT), search globally to fill up
        remaining_needed = DISPLAY_LIMIT - len(indian_profiles_for_this_keyword)
        if remaining_needed > 0:
            print(f"Still need {remaining_needed} profiles. Searching globally for '{keyword}' to top up...")
            global_results_raw = search_profiles(keyword, location='', num_results=remaining_needed * 2)  # Request more globally
            if global_results_raw:
                for profile in global_results_raw:
                    if len(global_profiles_for_this_keyword) >= remaining_needed:
                        break  # Stop if we've collected enough global profiles for the remaining need
                    if profile['link'] not in current_links_for_dedup:
                        global_profiles_for_this_keyword.append(profile)
                        current_links_for_dedup.add(profile['link'])
                print(f"Found {len(global_profiles_for_this_keyword)} unique global profiles for '{keyword}' (after de-duplication).")

        # Combine results for the current keyword: Indian first, then global, strictly limited to DISPLAY_LIMIT
        # This order ensures Indian profiles take precedence for display.
        combined_results_for_keyword = indian_profiles_for_this_keyword + global_profiles_for_this_keyword
        final_keyword_results_for_display = combined_results_for_keyword[:DISPLAY_LIMIT]
        all_found_profiles_for_display.extend(final_keyword_results_for_display)

        print(f"Final profiles for '{keyword}' (to be displayed): {len(final_keyword_results_for_display)}")
        print("---------------------------------------")

    # Add new unique profiles to the cache (across all keywords)
    for profile in all_found_profiles_for_display:
        unique_profiles_for_cache[profile['link']] = profile
    _profiles_cache = list(unique_profiles_for_cache.values())
    # Save updated cache to disk (history)
    with open(HISTORY_FILE, "w") as f:
        json.dump(_profiles_cache, f)

    if _profiles_cache:
        # --- AUTOMATIC EXCEL EXPORT ON SERVER ---
        try:
            excel_filename = "linkscout_latest_export.xlsx"
            export_to_excel(_profiles_cache, filename=excel_filename)
            print(f"Automatically exported {len(_profiles_cache)} profiles to {excel_filename}")
        except Exception as e:
            print(f"Error during automatic Excel export: {e}")
        # ----------------------------------------
    else:
        print("No profiles found for export.")

    if not all_found_profiles_for_display:
        raise HTTPException(status_code=404, detail="No profiles found for the given search terms.")

    return all_found_profiles_for_display # Return the combined and limited results for display

@app.get("/api/profiles", response_model=List[Profile])
async def get_current_profiles():
    """
    Returns the profiles from the last successful search.
    """
    if not _profiles_cache:
        raise HTTPException(status_code=404, detail="No profiles found. Please perform a search first.")
    return _profiles_cache


@app.get("/api/export/excel", response_class=Response)
async def download_excel_export():
    """
    Downloads the currently cached profiles as an Excel file.
    """
    if not _profiles_cache:
        raise HTTPException(status_code=404, detail="No profiles to export. Perform a search first.")

    output = io.BytesIO()
    df = pd.DataFrame(_profiles_cache)
    try:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='LinkedIn Profiles')
        output.seek(0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Excel file for download: {e}")

    headers = {
        "Content-Disposition": "attachment; filename=linkscout_download.xlsx",
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    }
    return Response(content=output.getvalue(), headers=headers)

@app.get("/api/export/csv", response_class=Response)
async def download_csv_export():
    """
    Downloads the currently cached profiles as a CSV file.
    """
    if not _profiles_cache:
        raise HTTPException(status_code=404, detail="No profiles to export. Perform a search first.")

    output = io.StringIO()
    df = pd.DataFrame(_profiles_cache)
    try:
        df.to_csv(output, index=False)
        output.seek(0)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create CSV file for download: {e}")

    headers = {
        "Content-Disposition": "attachment; filename=linkscout_download.csv",
        "Content-Type": "text/csv"
    }
    return Response(content=output.getvalue(), headers=headers)

@app.post("/api/export/google_sheets")
async def export_to_google_sheets_api():
    """
    Exports the currently cached profiles to Google Sheets.
    """
    if not _profiles_cache:
        raise HTTPException(status_code=404, detail="No profiles to export. Perform a search first.")

    success = export_to_google_sheets(_profiles_cache)
    if success:
        return {"message": "Profiles successfully exported to Google Sheets."}
    else:
        raise HTTPException(status_code=500, detail="Failed to export profiles to Google Sheets. Check server logs for details.")

@app.post("/api/open_links")
async def open_links_api():
    """
    Opens all cached LinkedIn profile links in the browser (on the server machine).
    """
    if not _profiles_cache:
        raise HTTPException(status_code=404, detail="No profiles to open. Perform a search first.")
    try:
        open_links_in_browser(_profiles_cache)
        return {"message": "Attempted to open all profile links in browser tabs."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open links: {e}")

@app.get("/history", response_class=HTMLResponse)
async def history_page():
    """
    Serves the search history page with download button.
    """
    return FileResponse("static/history.html")