from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import fitz  # PyMuPDF
import re
import os

app = Flask(__name__, static_folder='../frontend/build')

# CORS for frontend connection
CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}}, supports_credentials=True)

UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


### --- Enhanced Footer Removal --- ###
def remove_footer(text):
    footer_pattern = re.compile(r"(SFG\s?\d+|LEVEL\s?\d+|Forum\sLearning\sCentre|Delhi|Patna|Hyderabad|New Delhi|IAPL House|Pusa Road|Test\s\d+|contact@|academy|www\.|helpdesk@|address|ForumIAS)", re.IGNORECASE)
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines if not footer_pattern.search(line) and len(line.strip()) > 0]
    return "\n".join(cleaned_lines)


### --- Extract Text by Columns (Page-wise) --- ###
def extract_text_by_columns(pdf_path):
    doc = fitz.open(pdf_path)
    combined_text = ""

    try:
        for page_number, page in enumerate(doc):
            if page_number == 0:  # Skip the first page
                continue

            page_width = page.rect.width
            mid_point = page_width / 2

            left_rect = fitz.Rect(0, 0, mid_point, page.rect.height)
            right_rect = fitz.Rect(mid_point, 0, page_width, page.rect.height)

            left_column_text = remove_footer(page.get_text("text", clip=left_rect).strip())
            right_column_text = remove_footer(page.get_text("text", clip=right_rect).strip())

            combined_text += left_column_text + "\n" + right_column_text + "\n\n"
    finally:
        doc.close()  # Ensure PDF is closed

    return combined_text


### --- Extract Options --- ###
def extract_options(question_text_block):
    option_dict = {}

    option_pattern = re.compile(r"(?<!\()\b([a-dA-D]\))\s*(.+?)(?=\n[a-dA-D]\)|\n(?:Q\.?\s?\d+|\d+\)|$|Directions for the following|Passage I|Passage II|Read the following))", re.DOTALL)
    options = option_pattern.findall(question_text_block)

    for o in options:
        option_text = o[1].strip()
        option_text = re.sub(r"\bPage\s*\d+\b", "", option_text).strip()
        option_dict[o[0].strip()] = option_text

    return option_dict


### --- Extract Questions and Options --- ###
def extract_questions_from_text(text):
    questions_data = []
    question_pattern = re.compile(r"(?:Q\.?\s?\d+|\d+\))\s([\s\S]+?)(?=\n(?:[a-dA-D]\)|Directions for the following|Passage I|Passage II|Read the following|$))")
    questions = question_pattern.findall(text)

    if not questions:
        print("⚠️ No questions extracted. Check PDF format or extraction logic.")

    for i, question_text in enumerate(questions):
        question_text = question_text.strip()
        start_index = text.find(question_text)
        end_index = text.find(questions[i + 1].strip()) if i + 1 < len(questions) else len(text)
        question_text_block = text[start_index:end_index]
        question_text = re.sub(r"[ ]{2,}", " ", question_text).replace("\n", " \n")
        option_dict = extract_options(question_text_block)

        if not option_dict:
            print(f"⚠️ No options found for question: {question_text}")

        questions_data.append({
            "question": question_text,
            "options": option_dict if option_dict else None
        })

    print(f"✅ Total Questions Extracted: {len(questions_data)}")
    return questions_data


### --- API Endpoint for PDF Upload --- ###
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    pdf_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(pdf_path)

    try:
        extracted_text = extract_text_by_columns(pdf_path)
        questions = extract_questions_from_text(extracted_text)
        return jsonify({"questions": questions})
    except Exception as e:
        print(f"❗ Error during processing: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            os.remove(pdf_path)
            print("🧹 PDF deleted after processing")
        except Exception as e:
            print(f"❗ Error deleting file: {e}")


### --- Serve React Frontend --- ###
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')


if __name__ == '__main__':
    app.run(debug=True)
