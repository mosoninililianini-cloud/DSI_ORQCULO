import os
from flask import Flask, render_template, request, jsonify, send_file, session
from flask_cors import CORS
from dotenv import load_dotenv
import stripe
from utils.file_processor import process_file, get_file_preview
from utils.watermark import add_watermark_to_pdf
from utils.stripe_handler import create_payment_intent, verify_payment
import secrets

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
CORS(app)

# Configurar Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')

# Crear carpeta de uploads si no existe
os.makedirs('uploads', exist_ok=True)
os.makedirs('pdfs', exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html', stripe_key=STRIPE_PUBLISHABLE_KEY)

@app.route('/api/preview', methods=['POST'])
def preview_file():
    """Genera vista previa gratuita con marca de agua"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    try:
        preview_data = get_file_preview(file)
        return jsonify({
            'status': 'success',
            'preview': preview_data,
            'message': 'Vista previa con marca de agua (Versión freemium)'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/create-payment-intent', methods=['POST'])
def create_payment():
    """Crea una intención de pago en Stripe"""
    data = request.get_json()
    amount = data.get('amount', 999)  # Precio por defecto: $9.99
    
    try:
        intent = create_payment_intent(amount)
        return jsonify({
            'client_secret': intent['client_secret'],
            'publishable_key': STRIPE_PUBLISHABLE_KEY
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/verify-payment', methods=['POST'])
def verify_pago():
    """Verifica el pago y genera PDF descargable"""
    data = request.get_json()
    payment_intent_id = data.get('payment_intent_id')
    file_data = data.get('file_data')
    
    try:
        is_valid = verify_payment(payment_intent_id)
        
        if is_valid:
            # Generar PDF sin marca de agua
            pdf_path = process_file(file_data, watermark=False)
            
            # Guardar registro de pago
            session['payment_verified'] = True
            session['pdf_path'] = pdf_path
            
            return jsonify({
                'status': 'success',
                'message': 'Pago verificado. PDF listo para descargar',
                'download_url': f'/api/download/{os.path.basename(pdf_path)}'
            })
        else:
            return jsonify({'error': 'Payment verification failed'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/download/<filename>', methods=['GET'])
def download_pdf(filename):
    """Descarga el PDF pagado"""
    if 'payment_verified' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    try:
        pdf_path = os.path.join('pdfs', filename)
        return send_file(pdf_path, as_attachment=True, mimetype='application/pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/health', methods=['GET'])
def health():
    """Health check para Railway/Render"""
    return jsonify({'status': 'ok', 'service': 'Oraculo DSI API'}), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=os.getenv('DEBUG', False))