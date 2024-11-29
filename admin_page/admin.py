import json
import os
from flask import Flask, render_template, request, redirect, url_for
from flask import send_from_directory
DOWNLOADS_DIR = os.path.join(os.environ['USERPROFILE'], 'Downloads')  # For Windows
app = Flask(__name__)

# Path to the JSON file for storing technician data
TECHNICIAN_FILE = "admin_page/technicians.json"
PDF_DIR = os.path.join(os.path.dirname(__file__), 'static', 'pdfs')
os.makedirs(PDF_DIR, exist_ok=True)





def load_technicians():
    """Load technician data from the JSON file."""
    try:
        with open(TECHNICIAN_FILE, "r") as file:
            data = json.load(file)
        print("Loaded Technicians:", data.get("technicians", []))  # Debug log
        return data.get("technicians", [])
    except FileNotFoundError:
        print("technicians.json not found!")  # Debug log
        return []

def save_technicians(technicians):
    """Save the list of technicians to the JSON file."""
    with open(TECHNICIAN_FILE, "w") as file:
        json.dump({"technicians": technicians}, file, indent=4)
    print("Saved Technicians:", technicians)  # Debug log


@app.route('/')
def login():
    """Render the login page."""
    return render_template('login.html', error=None)

@app.route('/admin_dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    """Render the admin dashboard after successful login."""
    technicians = load_technicians()  # Get the list of technicians
    total_technicians = len(technicians)  # Count technicians

    try:
        pdf_files = [f for f in os.listdir(DOWNLOADS_DIR) if f.endswith('.pdf')]
        total_pdfs = len(pdf_files)  # Count PDF files
    except Exception as e:
        print("Error reading PDF files:", e)
        total_pdfs = 0

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == "Admin" and password == "adminrs123":
            return render_template('admin_dashboard.html', total_technicians=total_technicians, total_pdfs=total_pdfs)
        else:
            return render_template('login.html', error="Invalid username or password.")

    return render_template('admin_dashboard.html', total_technicians=total_technicians, total_pdfs=total_pdfs)


@app.route('/manageTechnician')
def manage_technician():
    technicians = load_technicians()
    return render_template('manageTechnician.html', technicians=technicians)

@app.route('/addTechnician', methods=['POST'])
def add_technician():
    technicians = load_technicians()
    new_technician = request.form.get("new_technician").strip()
    if new_technician and new_technician not in technicians:
        technicians.append(new_technician)
        save_technicians(technicians)  # Save changes to JSON
    return redirect(url_for('manage_technician'))


@app.route('/editTechnician', methods=['POST'])
def edit_technician():
    """Edit an existing technician's name."""
    technicians = load_technicians()
    old_name = request.form.get("old_name").strip()
    new_name = request.form.get("new_name").strip()
    if old_name in technicians and new_name:
        technicians[technicians.index(old_name)] = new_name
        save_technicians(technicians)
    return redirect(url_for('manage_technician'))

@app.route('/deleteTechnician', methods=['POST'])
def delete_technician():
    """Delete a technician from the list."""
    technicians = load_technicians()
    name_to_delete = request.form.get("name_to_delete").strip()
    if name_to_delete in technicians:
        technicians.remove(name_to_delete)
        save_technicians(technicians)
    return redirect(url_for('manage_technician'))

@app.route('/managePDF')
def manage_pdf():
    """Render the Manage PDF Files page with the list of files from the Downloads folder."""
    try:
        pdf_files = [f for f in os.listdir(DOWNLOADS_DIR) if f.endswith('.pdf')]
        print("PDF Files Found in Downloads:", pdf_files)  # Debugging
        return render_template('managePDF.html', pdf_files=pdf_files)
    except Exception as e:
        print("Error reading PDF files:", e)
        return "Error reading PDF files.", 500

@app.route('/view_pdf/<filename>')
def view_pdf(filename):
    """Serve the PDF file for viewing."""
    return send_from_directory(DOWNLOADS_DIR, filename)

@app.route('/delete_pdf', methods=['POST'])
def delete_pdf():
    """Delete a specified PDF file from the Downloads folder."""
    filename = request.form.get("filename")
    if filename:
        file_path = os.path.join(DOWNLOADS_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
    return redirect(url_for('manage_pdf'))


@app.route('/form')
def form():
    """Render the form page with the current list of technicians."""
    technicians = load_technicians()  # Load technicians from JSON
    return render_template('form.html', technicians=technicians)




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
