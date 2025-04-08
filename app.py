from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS
import os
import requests
import datetime
import PyPDF2
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# Load environment variables
load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GNEWS_API_KEY = os.getenv("GNEWS_API_KEY")
CURRENTS_API_KEY = os.getenv("CURRENTS_API_KEY")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://your-frontend-url.com")

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

chat_history = []

country_codes = {
    "united states": "us", "india": "in", "united kingdom": "gb",
    "canada": "ca", "germany": "de", "france": "fr",
    "australia": "au", "japan": "jp", "china": "cn"
}

@app.route('/')
def home():
    return redirect(FRONTEND_URL, code=302)

@app.route('/datetime', methods=['GET'])
def get_datetime():
    now = datetime.datetime.now()
    date = now.strftime('%A, %B %d, %Y')
    time = now.strftime('%I:%M:%S %p')
    return jsonify({'response': f"📅 Date: {date} | ⏰ Time: {time}"})


# 📰 Fetch fallback news from Currents API
def fetch_currents_news(query=None, country=None):
    headers = {
        'Authorization': CURRENTS_API_KEY
    }
    params = {
        'language': 'en'
    }
    if query:
        params['keywords'] = query
    elif country:
        params['country'] = country

    response = requests.get("https://api.currentsapi.services/v1/latest-news", headers=headers, params=params)
    data = response.json()
    articles = data.get('news', [])[:5]
    return '\n'.join(f"📰 {a['title']} - {a.get('author') or 'Unknown'}" for a in articles)


# 🤖 Chatbot using Groq API
def handle_chat(message):
    chat_history.append({"role": "user", "content": message})
    system_prompt = {"role": "system", "content": "You are Nova X, a helpful AI assistant."}
    trimmed_history = chat_history[-12:]

    payload = {
        "model": "llama3-70b-8192",
        "messages": [system_prompt] + trimmed_history,
        "temperature": 1,
        "max_tokens": 1024,
        "top_p": 1,
        "stream": False
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }

    response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
    data = response.json()
    reply = data['choices'][0]['message']['content']
    chat_history.append({"role": "assistant", "content": reply})
    return reply

@app.route('/chat', methods=['POST'])
@app.route('/api/ask', methods=['POST'])
def chat():
    message = request.json.get('message', '').strip()
    if not message:
        return jsonify({'error': '⚠️ Message is required'}), 400
    try:
        reply = handle_chat(message)
        return jsonify({'response': reply})
    except Exception:
        return jsonify({'response': '❌ Error connecting to Groq Chat API.'}), 500


@app.route('/reset-memory', methods=['POST'])
def reset_memory():
    chat_history.clear()
    return jsonify({"message": "🧠 Memory cleared!"})


# 🌍 News by topic with fallback to Currents
@app.route('/news/topic', methods=['GET'])
def news_by_topic():
    topic = request.args.get('topic', '')
    if not topic:
        return jsonify({'response': '⚠️ Topic required.'}), 400

    url = f"https://gnews.io/api/v4/search?q={topic}&token={GNEWS_API_KEY}"
    try:
        response = requests.get(url)
        articles = response.json().get('articles', [])[:5]
        if not articles:
            raise ValueError("Fallback to Currents")

        formatted = '\n'.join(f"🗞️ {a['title']} - {a['source']['name']}" for a in articles)
        return jsonify({'response': formatted})
    except:
        try:
            formatted = fetch_currents_news(query=topic)
            return jsonify({'response': formatted or "No news found for this topic."})
        except:
            return jsonify({'response': '❌ Error fetching topic news.'}), 500


# 🗺️ News by country with fallback to Currents
@app.route('/news/country', methods=['GET'])
def news_by_country():
    country = request.args.get('country', '').lower()
    code = country_codes.get(country)
    if not code:
        return jsonify({'response': '⚠️ Unsupported country.'}), 400

    url = f"https://gnews.io/api/v4/top-headlines?country={code}&token={GNEWS_API_KEY}"
    try:
        response = requests.get(url)
        articles = response.json().get('articles', [])[:5]
        if not articles:
            raise ValueError("Fallback to Currents")

        formatted = '\n'.join(f"📰 {a['title']} - {a['source']['name']}" for a in articles)
        return jsonify({'response': formatted})
    except:
        try:
            formatted = fetch_currents_news(country=code)
            return jsonify({'response': formatted or "No news found."})
        except:
            return jsonify({'response': '❌ Error fetching country news.'}), 500


@app.route('/pdf', methods=['POST'])
def upload_pdf():
    file = request.files.get('pdf')
    if not file:
        return jsonify({'text': None}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ''.join(page.extract_text() or '' for page in reader.pages)
        return jsonify({'text': text})
    except Exception:
        return jsonify({'text': None}), 500


@app.route('/search-web', methods=['POST'])
def search_web():
    query = request.json.get('query', '').strip()
    if not query:
        return jsonify({'results': ["No query provided."]}), 400

    try:
        response = requests.get(f"https://html.duckduckgo.com/html/?q={query}", headers={
            "User-Agent": "Mozilla/5.0"
        })
        soup = BeautifulSoup(response.text, 'html.parser')
        results = []

        for result in soup.select('.result__title'):
            a_tag = result.find('a')
            if a_tag:
                title = a_tag.get_text(strip=True)
                url = a_tag.get('href')
                results.append({'title': title, 'url': url})

        if not results:
            return jsonify({'results': [f'No results found for "{query}".']})
        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': f'Web search failed: {str(e)}'}), 500


@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('public', path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
