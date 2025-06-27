import requests
import pandas as pd
import webbrowser
import gspread
from google.oauth2.service_account import Credentials
import os # Import os for environment variables
import json # For parsing potential JSON error responses

# IMPORTANT: Set your Serper.dev API key securely
# Use environment variable for Serper API key
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

SHEET_NAME = "LinkScout Leads" # Name of your Google Sheet
CREDS_FILE = "credentials.json" # Path to your service account credentials file

def search_profiles(keyword: str, location: str = 'in', num_results: int = 100) -> list[dict]:
    """
    Searches LinkedIn profiles using the Serper.dev API, with optional location and result limit.
    :param keyword: The search term (e.g., "venture scout").
    :param location: The 'gl' (geolocation) parameter for Serper.dev. Defaults to 'in' (India).
                     Use an empty string '' for global/no specific country bias.
    :param num_results: The number of results to request from Serper.dev (max 100 per query for most plans).
    :return: A list of dictionaries, each representing a LinkedIn profile.
    """
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'} # Ensure Content-Type header

    # Basic validation for API key
    if not SERPER_API_KEY or SERPER_API_KEY == "YOUR_ACTUAL_SERPER_API_KEY_HERE":
        print("Error: SERPER_API_KEY is not set or is still the placeholder. Please configure it.")
        return []

    payload = {'q': f'site:linkedin.com/in/ "{keyword}"', 'num': num_results}

    # Add 'gl' only if location is provided
    if location:
        payload['gl'] = location

    try:
        res = requests.post('https://google.serper.dev/search', json=payload, headers=headers)
        
        # Debugging: Print status code and response text for all responses
        print(f"DEBUG: Serper API call for '{keyword}' (loc: '{location}', num: {num_results}) - Status: {res.status_code}")
        # print(f"DEBUG: Serper API Raw Response: {res.text[:500]}...") # Uncomment for very detailed debug

        res.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        
        data = res.json().get('organic', [])
    except requests.exceptions.HTTPError as e:
        print(f"Serper API HTTP Error for '{keyword}' (location: '{location}'): {e}")
        try:
            error_details = e.response.json()
            print(f"Serper API Error Details (JSON): {json.dumps(error_details, indent=2)}")
        except json.JSONDecodeError:
            print(f"Serper API Error Details (Raw Text): {e.response.text}")
        return []
    except requests.exceptions.RequestException as e:
        print(f"Serper API network error for '{keyword}' (location: '{location}'): {e}")
        return []
    except ValueError as e: # Catches JSON decoding errors
        print(f"Failed to decode Serper API response for '{keyword}' (location: '{location}'): {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during search for '{keyword}' (location: '{location}'): {e}")
        return []

    results = []
    for item in data:
        title = item.get("title", "")
        link = item.get("link", "")
        if not link or "linkedin.com/in/" not in link:
            continue
        parts = title.split(" - ")
        name = parts[0].strip()
        role = "Unknown"
        if len(parts) > 1:
            potential_role = " - ".join(parts[1:])
            # Refine role extraction to clean up common LinkedIn suffixes
            if "LinkedIn" in potential_role:
                role = potential_role.split(" | ")[0].strip() # Take part before " | LinkedIn"
            else:
                role = potential_role.strip()
            # Further cleanup for common job board/location suffixes that might stick
            role = role.replace(" (Remote)", "").replace(" (Hybrid)", "").replace(" (On-site)", "").strip()
            if " in " in role and " | " not in role: # "Role in Location" format
                role = role.split(" in ")[0].strip()


        results.append({"name": name, "role": role, "link": link})
    return results

def export_to_csv(data: list[dict], filename: str = "linkscout_export.csv") -> str:
    """
    Exports profile data to a CSV file.
    """
    if not data:
        return "No data to export (CSV)."
    df = pd.DataFrame(data)
    try:
        df.to_csv(filename, index=False)
        print(f"DEBUG: Successfully exported to CSV: {filename}")
        return filename
    except Exception as e:
        print(f"ERROR: Failed to export to CSV '{filename}': {e}")
        return f"Error exporting to CSV: {e}"

def export_to_excel(data: list[dict], filename: str = "linkscout_export.xlsx") -> str:
    """
    Exports profile data to an Excel file.
    """
    if not data:
        return "No data to export (Excel)."
    df = pd.DataFrame(data)
    try:
        df.to_excel(filename, index=False, engine='xlsxwriter') # Explicitly use xlsxwriter
        print(f"DEBUG: Successfully exported to Excel: {filename}")
        return filename
    except Exception as e:
        print(f"ERROR: Failed to export to Excel '{filename}': {e}")
        return f"Error exporting to Excel: {e}"

def export_to_google_sheets(data: list[dict]) -> bool:
    """
    Exports profile data to a Google Sheet.
    Requires 'credentials.json' and the sheet to be shared with the service account.
    """
    if not os.path.exists(CREDS_FILE):
        print(f"ERROR: Google Sheets credentials file '{CREDS_FILE}' not found. Skipping export.")
        return False
    if not data:
        print("DEBUG: No data provided for Google Sheets export.")
        return False

    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = Credentials.from_service_account_file(CREDS_FILE, scopes=scope)
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1 # Opens the first sheet

        sheet.clear()
        sheet.append_row(["Name", "Role", "LinkedIn URL"])

        rows_to_append = [[row["name"], row["role"], row["link"]] for row in data]
        sheet.append_rows(rows_to_append)
        print(f"DEBUG: Successfully exported {len(data)} profiles to Google Sheet '{SHEET_NAME}'.")
        return True
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"ERROR: Google Sheet '{SHEET_NAME}' not found or not shared with service account. Please check sheet name and sharing permissions.")
        return False
    except gspread.exceptions.APIError as e:
        print(f"ERROR: Google Sheets API error: {e.response.text if hasattr(e.response, 'text') else e}")
        return False
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during Google Sheets export: {e}")
        return False

def open_links_in_browser(data: list[dict]):
    """
    Opens LinkedIn profile links in new browser tabs.
    """
    if not data:
        print("DEBUG: No data to open links.")
        return
    for i, row in enumerate(data):
        print(f"DEBUG: Opening link {i+1}/{len(data)}: {row['link']}")
        webbrowser.open_new_tab(row["link"])
    print("DEBUG: Finished attempting to open all links.")