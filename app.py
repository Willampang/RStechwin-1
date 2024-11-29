import os  # For managing file paths and environment variables
import json  # For working with JSON data
from flask import Flask, render_template, request, send_file, jsonify  # Flask for web handling
from io import BytesIO  # In-memory file management
from PIL import Image  # For image handling
import fitz  # PyMuPDF for PDF processing
import base64  # For decoding base64 strings
import requests  # For interacting with APIs (e.g., Google Sheets)
from textblob import TextBlob  # For AI-based spell checking
import shutil  # Add this import at the top of your code


# Ensure compatibility across environments (Windows/Linux)
DOWNLOADS_DIR = os.path.join(os.environ.get('USERPROFILE') or os.environ.get('HOME') or '/tmp', 'Downloads')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)  # Create the directory if it doesn't exist

# Flask app initialization
app = Flask(__name__)

# ------------------------------
# Paths and Configuration
# ------------------------------
# Path to the static PDF template file
TEMPLATE_PATH = os.path.join(app.root_path, 'static', 'SDO_report_web.pdf')

# Paths for writable output files (compatible with Render's environment)
OUTPUT_TEMP_PATH = os.path.join('/tmp', 'output_temp.pdf')  # Temporary output for PDF merging
OUTPUT_PATH = os.path.join('/tmp', 'filled_SDO_report.pdf')  # Final filled PDF

# Directory for storing signatures temporarily
SIGNATURE_DIR = os.path.join('/tmp', 'signatures')
os.makedirs(SIGNATURE_DIR, exist_ok=True)  # Create if it doesn't exist

# Path to track DO numbers locally
DO_NO_FILE = os.path.join(app.root_path, 'do_no.txt')

# Path to technician data JSON file
TECHNICIAN_FILE = os.path.join(app.root_path, "admin_page", "technicians.json")

# Google Sheets Web App URL for integration
GOOGLE_SHEET_WEB_APP_URL = (
    "https://script.google.com/macros/s/AKfycbyfYgiOYjHPfDtk1sJm7iS8UPTNVEkXKgpqZ8DRhYNQRH9dH0ki7Ppx3rgvfjuSB54O/exec"
)


def load_technicians():
    """Load technician data from the JSON file."""
    try:
        with open(TECHNICIAN_FILE, "r") as file:
            data = json.load(file)
        return data.get("technicians", [])
    except FileNotFoundError:
        return []


def get_next_do_no():
    """Fetch the next available DO No. by checking Google Sheets."""
    try:
        # Fetch all existing DO numbers from Google Sheets
        response = requests.get(GOOGLE_SHEET_WEB_APP_URL, params={"action": "get_all_do_no"})
        print(f"Request URL: {response.url}")  # Debugging: Log request URL
        print(f"Response Status Code: {response.status_code}")  # Debugging: Log status code
        print(f"Response Text: {response.text}")  # Debugging: Log response text

        if response.status_code == 200:
            try:
                # Parse the JSON response
                response_data = response.json()
                existing_numbers = response_data.get("numbers", [])

                if not isinstance(existing_numbers, list):
                    raise ValueError("Expected a list in 'numbers'")

                # Ensure all items are integers
                existing_numbers = [int(num) for num in existing_numbers]
                existing_numbers.sort()

                # Find the first available number
                next_number = 1001
                while next_number in existing_numbers:
                    next_number += 1
                return next_number
            except (ValueError, TypeError) as e:
                print(f"Error processing JSON response: {e}")
                return 1001
        else:
            print(f"Error fetching DO numbers: {response.text}")
            return 1001
    except Exception as e:
        print(f"Exception occurred: {e}")
        return 1001


def check_number_in_google_sheets(do_no):
    """Checks if the given DO No. already exists in Google Sheets."""
    try:
        response = requests.get(GOOGLE_SHEET_WEB_APP_URL, params={"action": "check_do_no", "do_no": do_no})
        if response.status_code == 200:
            result = response.json()  # Parse the JSON response
            return result.get("exists", False)
        else:
            print(f"Failed to check Google Sheets for DO No. {do_no}: {response.text}")
            return False
    except requests.exceptions.RequestException as req_error:
        print(f"Request error: {req_error}")
        return False
    except ValueError as json_error:
        print(f"JSON error: {json_error} | Response content: {response.text}")
        return False


@app.route('/')
def form():
    """Render the form with the next available DO No."""
    print("Serving form.html")  # Debugging output
    do_no = get_next_do_no()
    technicians = load_technicians()
    return render_template('form.html', do_no=do_no, technicians=technicians)



@app.route('/spellcheck', methods=['POST'])
def spellcheck():
    """AI spell-checking route for multi-word sentences."""
    try:
        data = request.json
        text = data.get('text', '')
        if not text.strip():
            return jsonify({'corrected': text})  # Return original text if empty

        # Use TextBlob for spell-checking
        blob = TextBlob(text)
        corrected_text = str(blob.correct())  # Correct the entire sentence
        return jsonify({'corrected': corrected_text})
    except Exception as e:
        return jsonify({'corrected': None}), 500


@app.route('/submit', methods=['POST'])
def submit():
    """
    Handles form submission, generates PDF, and sends data to Google Sheets.
    """
    try:
        # Step 1: Collect and organize form data
        form_data = {
            "SDO #": request.form.get("sdo_no", "0000"),
            "Project Site": request.form.get("project_site", "").strip(),
            "DO No.": request.form.get("do_no", "").strip(),
            "Date": request.form.get("date", "").strip(),
            "Technician": request.form.get("technician", "").strip(),
            "Check In-Time": request.form.get("check_in_time", "").strip(),
            "Check Out-Time": request.form.get("check_out_time", "").strip(),
            "Task Objectives": request.form.get("task_objectives", "").strip(),
            "System Type": request.form.getlist("system_type"),
            "Type": request.form.getlist("type"),
            "Materials": request.form.get("materials", "").strip(),
            "Special Instructions": request.form.get("special_instructions", "").strip(),
            "Reported by Name": request.form.get("reported_by", "").strip(),
            "Reported Date": request.form.get("date", "").strip(),
            "Client's Signature Name": request.form.get("client_name", "").strip(),
            "Client's Position": request.form.get("position", "").strip(),
        }

        # Collect scope data dynamically
        for i in range(1, 7):
            form_data[f"Scope {i} Location"] = request.form.get(f"scope_{i}_location", "").strip()
            form_data[f"Scope {i} Status"] = request.form.get(f"scope_{i}_status", "").strip()
            form_data[f"Scope {i} Description"] = request.form.get(f"scope_{i}_description", "").strip()

        # Validate required fields
        required_fields = ["DO No.", "Project Site", "Date", "Technician"]
        missing_fields = [field for field in required_fields if not form_data[field]]
        if missing_fields:
            return f"Error: Missing required fields: {', '.join(missing_fields)}", 400

        # Step 2: Generate the overlay PDF and merge with template
        overlay_pdf = create_overlay_pdf(form_data)
        merge_pdfs_with_images(overlay_pdf, TEMPLATE_PATH, OUTPUT_TEMP_PATH, request.files, form_data)
        add_signatures_to_pdf(
            OUTPUT_TEMP_PATH,
            OUTPUT_PATH,
            request.form.get("reported_by_signature"),
            request.form.get("client_signature")
        )

        # Step 3: Prepare data for Google Sheets
        google_sheet_data = {
            "sdo_id": form_data["DO No."],
            "project_site": form_data["Project Site"],
            "date": form_data["Date"],
            "technician_name": form_data["Technician"],
            "check_in_time": form_data["Check In-Time"],
            "check_out_time": form_data["Check Out-Time"],
            "task_objective": form_data["Task Objectives"],
            "type": ", ".join(form_data["Type"]),
            "system_type": ", ".join(form_data["System Type"]),
        }

        print(f"Google Sheet Data: {google_sheet_data}")
        headers = {"Content-Type": "application/json"}

        # Step 4: Send data to Google Sheets
        response = requests.post(GOOGLE_SHEET_WEB_APP_URL, json=google_sheet_data)
        print(f"Sending data to Google Sheets: {google_sheet_data}")
        print(f"Response from Google Sheets: {response.status_code}, {response.text}")

        if response.status_code != 200:
            return f"Error: Failed to send data to Google Sheets. Response: {response.text}", 500

        # Save the filled PDF in the Downloads directory
        pdf_filename = f"{form_data['DO No.']}_filled_SDO_report.pdf"
        pdf_path = os.path.join(DOWNLOADS_DIR, pdf_filename)

        # Use shutil.move instead of os.rename to avoid cross-device link errors
        shutil.move(OUTPUT_PATH, pdf_path)

        # Return the filled PDF
        return send_file(
            pdf_path,
            as_attachment=True,
            download_name=pdf_filename,
            mimetype="application/pdf"
        )
    except Exception as e:
        print(f"Error during form submission: {e}")
        return f"Error: Could not process the form submission. Details: {e}", 500


    # Serve the filled PDF to the user
    return send_file(OUTPUT_PATH, as_attachment=True, download_name='filled_SDO_report.pdf', mimetype='application/pdf')


def create_overlay_pdf(data):
    """Creates an overlay PDF with form data and returns it as a BytesIO object."""
    buffer = BytesIO()
    doc = fitz.open()  # Create a new PDF
    page = doc.new_page(width=595, height=842)  # Standard A4 size

    # Coordinates for each field on the PDF template
    coordinates = {
        "SDO #": (620, 20),
        "Project Site": (160, 113),
        "DO No.": (165, 132),
        "Technician": (160, 145),
        "Task Objectives": (149, 161),
        "Date": (510, 115),
        "Check In-Time": (510, 131),
        "Check Out-Time": (510, 146),
        "Materials": (50, 690),
        "Special Instructions": (50, 750),
        
        "Reported by Name": (430, 744),
        "Reported Date": (430, 755),
        "Client's Signature Name": (531, 744),
        "Client's Position": (531, 755)
    }

    # Checkbox coordinates for System Types
    system_type_positions = {
        "CCTV": (116, 169),
        "Door Access": (152, 170),
        "Lift Access": (210, 170),
        "Barrier Gate": (263, 170),
        "Intercom": (320, 170),
        "Networking": (364, 170),
        "Others": (418, 170)
    }

    # Updated Checkbox coordinates for Types (Service, Installation, Maintenance)
    type_positions = {
        "Service": (530, 53),
        "Installation": (540, 68),
        "Maintenance": (550, 81)
    }

    # Insert text data for basic fields
    for field, coord in coordinates.items():
        text = data.get(field, "")
        if text:
            font_size = 8 if "Scope" in field else 10
            page.insert_text(coord, text, fontsize=font_size)

    # Insert checkmarks for selected system types
    for item in data.get("System Type", []):
        if item in system_type_positions:
            x, y = system_type_positions[item]
            page.insert_text((x + 2, y), "/", fontsize=8)

    # Insert checkmarks for selected service types
    for item in data.get("Type", []):
        if item in type_positions:
            x, y = type_positions[item]
            page.insert_text((x + 2, y), "/", fontsize=8)

    # Save overlay PDF to buffer
    doc.save(buffer)
    buffer.seek(0)
    return buffer

def save_signature_image(base64_string, filename):
    """Saves a base64-encoded signature as a PNG file with a transparent background."""
    if not base64_string:
        print(f"No Base64 string provided for {filename}")
        return None

    if "," in base64_string:
        base64_data = base64_string.split(",")[1]
    else:
        base64_data = base64_string

    missing_padding = len(base64_data) % 4
    if missing_padding:
        base64_data += '=' * (4 - missing_padding)

    try:
        image_data = BytesIO(base64.b64decode(base64_data))
        signature = Image.open(image_data).convert("RGBA")

        transparent_bg = Image.new("RGBA", signature.size, (255, 255, 255, 0))
        transparent_bg.paste(signature, (0, 0), signature)

        file_path = os.path.join(SIGNATURE_DIR, filename)
        transparent_bg.save(file_path, "PNG")

        print(f"Signature saved at {file_path}")  # Debug statement
        return file_path
    except Exception as e:
        print(f"Error decoding Base64 string for {filename}: {e}")
        return None


def merge_pdfs_with_images(overlay_pdf, template_path, output_temp_path, files, form_data):
    template = fitz.open(template_path)
    overlay = fitz.open(stream=overlay_pdf.getvalue(), filetype="pdf")
    template[0].show_pdf_page(template[0].rect, overlay, 0)

    image_positions = [
        (60, 220, 190, 325),  # Scope 1
        (250, 220, 380, 325),  # Scope 2
        (430, 220, 560, 325),  # Scope 3
        (60, 435, 190, 540),   # Scope 4
        (250, 435, 380, 540),  # Scope 5
        (430, 435, 560, 540),  # Scope 6
    ]

    scope_text_positions = [
        {"location": (130, 193), "status": (130, 203)},  # Scope 1
        {"location": (295, 193), "status": (295, 203)},  # Scope 2
        {"location": (475, 193), "status": (475, 203)},  # Scope 3
        {"location": (130, 404), "status": (130, 416)},  # Scope 4
        {"location": (295, 404), "status": (295, 416)},  # Scope 5
        {"location": (475, 404), "status": (475, 416)},  # Scope 6
    ]

    for i in range(1, 7):
        image_file = files.get(f"scope_{i}_image")
        if image_file:
            img = Image.open(image_file).resize((130, 130), Image.LANCZOS)
            img_stream = BytesIO()
            img.save(img_stream, format="PNG")
            img_stream.seek(0)

            x0, y0, x1, y1 = image_positions[i - 1]
            template[0].insert_image(fitz.Rect(x0, y0, x1, y1), stream=img_stream)

            description = form_data.get(f"Scope {i} Description", "")
            if description:
                desc_position = (x0, y1 + 15)
                template[0].insert_text(desc_position, description, fontsize=8)

            location = form_data.get(f"Scope {i} Location", "")
            status = form_data.get(f"Scope {i} Status", "")
            if location:
                template[0].insert_text(scope_text_positions[i - 1]["location"], location, fontsize=8)
            if status:
                template[0].insert_text(scope_text_positions[i - 1]["status"], status, fontsize=8)

    template.save(output_temp_path)
    template.close()

def add_signatures_to_pdf(pdf_path, output_path, reported_by_signature, client_signature):
    """Adds 'Reported by' and 'Client's Signature' images to the PDF at specific locations."""

    # Save signatures as PNGs with transparent backgrounds
    reported_by_path = save_signature_image(reported_by_signature, "reported_by.png")
    client_signature_path = save_signature_image(client_signature, "client_signature.png")

    print(f"Reported By Signature Path: {reported_by_path}")  # Debug statement
    print(f"Client Signature Path: {client_signature_path}")  # Debug statement

    # Open the existing PDF
    doc = fitz.open(pdf_path)

    # Define the coordinates for the signatures
    reported_by_position = (370, 560, 480, 770)  # Coordinates for 'Reported by' signature
    client_signature_position = (460, 640, 590, 700)  # Coordinates for 'Client's Signature'

    # Insert "Reported by" signature
    if reported_by_path:
        doc[0].insert_image(fitz.Rect(*reported_by_position), filename=reported_by_path)

    # Insert "Client's Signature"
    if client_signature_path:
        doc[0].insert_image(fitz.Rect(*client_signature_position), filename=client_signature_path)

    # Save the PDF with the signatures to the final output path
    doc.save(output_path)
    doc.close()



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
