from flask import Flask, request, render_template, send_file
import pandas as pd
from io import BytesIO
import requests
from PyPDF2 import PdfReader
from docx import Document
import google.generativeai as gemini_ai
import os

app = Flask(__name__)


gemini_ai.api_key = os.getenv('GOOGLE_API_KEY')

def fetch_text_from_url(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.text

def parse_txt_file(file):
    return file.read().decode('utf-8')

def parse_pdf_file(file):
    reader = PdfReader(file)
    text = ''
    for page in reader.pages:
        text += page.extract_text()
    return text

def parse_docx_file(file):
    doc = Document(file)
    text = ''
    for paragraph in doc.paragraphs:
        text += paragraph.text + '\n'
    return text

def split_text(text, max_chunk_size):
    """Split text into chunks of a maximum size."""
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0

    for word in words:
        word_size = len(word) + 1  # +1 for the space
        if current_size + word_size > max_chunk_size:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_size = word_size
        else:
            current_chunk.append(word)
            current_size += word_size

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks

def generate_mcqs(text):
    max_chunk_size = 1000  # Adjust the chunk size if needed
    chunks = split_text(text, max_chunk_size)
    mcqs = []

    for chunk in chunks:
        prompt = f"Generate multiple-choice questions from the following text:\n{chunk}\n\nQuestions should include 4 options with one correct answer clearly indicated. Your output should be in {{\"question_id\": \"id of question\", \"question\": \"generated question\", \"options\": \"list of options\",\"correct_answer\":\"corrected answer\"}}"
        # response = gemini_ai.GenerativeModel(model_name="models/gemini-1.5-pro", prompt=prompt)
        model = gemini_ai.GenerativeModel(model_name='gemini-1.5-flash')
        response = model.generate_content(prompt)
        mcqs_text = response.text
        # mcqs_text = response['choices'][0]['text']

        # Simple parser to extract questions and options from the generated text
        questions = mcqs_text.split('Question:')
        for question in questions[1:]:
            parts = question.split('\n')
            question_text = parts[0].strip()
            options = [option.strip() for option in parts[1:5]]
            correct_answer = parts[5].replace('Correct answer:', '').strip()
            mcqs.append({
                'question': question_text,
                'options': options,
                'correct_answer': correct_answer
            })
    return mcqs

def format_mcqs(mcqs, source, topic, difficulty):
    formatted_mcqs = []
    for mcq in mcqs:
        formatted_mcqs.append({
            'Question': mcq['question'],
            'Options': mcq['options'],
            'Correct Answer': mcq['correct_answer'],
            'Source': source,
            'Topic': topic,
            'Difficulty': difficulty
        })
    return pd.DataFrame(formatted_mcqs)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    source = request.form['source']
    topic = request.form['topic']
    difficulty = request.form['difficulty']
    url = request.form.get('url')
    file = request.files.get('file')
    text = ''

    if url:
        text = fetch_text_from_url(url)
    elif file:
        if file.filename.endswith('.txt'):
            text = parse_txt_file(file)
        elif file.filename.endswith('.pdf'):
            text = parse_pdf_file(file)
        elif file.filename.endswith('.docx'):
            text = parse_docx_file(file)
        else:
            return "Unsupported file format", 400

    if not text:
        return "No text data provided", 400

    mcqs = generate_mcqs(text)
    formatted_mcqs = format_mcqs(mcqs, source, topic, difficulty)
    return render_template('mcqs.html', tables=[formatted_mcqs.to_html(classes='data')], titles=formatted_mcqs.columns.values)

# @app.route('/export', methods=['POST'])
# def export():
#     format = request.form['format']
#     data = request.form['data']
#     df = pd.read_json(data)

#     if format == 'csv':
#         output = BytesIO()
#         df.to_csv(output)
#         output.seek(0)
#         return send_file(output, mimetype='text/csv', download_name='mcqs.csv', as_attachment=True)
#     elif format == 'json':
#         return df.to_json(), 200, {'Content-Type': 'application/json'}
#     elif format == 'txt':
#         return df.to_string(), 200, {'Content-Type': 'text/plain'}
#     else:
#         return "Unsupported export format", 400

@app.route('/export', methods=['POST'])
def export():
    format = request.form['format']
    data = request.form['data']
    
    try:
        # Ensure the data received is a valid JSON string
        df = pd.read_json(data)
    except ValueError as e:
        return f"Invalid JSON data: {str(e)}", 400
    
    if format == 'csv':
        output = BytesIO()
        df.to_csv(output, index=False)
        output.seek(0)
        return send_file(output, mimetype='text/csv', download_name='mcqs.csv', as_attachment=True)
    elif format == 'json':
        return df.to_json(orient='records'), 200, {'Content-Type': 'application/json'}
    elif format == 'txt':
        return df.to_string(index=False), 200, {'Content-Type': 'text/plain'}
    else:
        return "Unsupported export format", 400



if __name__ == '__main__':
    app.run(debug=True)