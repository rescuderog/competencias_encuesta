import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import hmac
import secrets
import random

app = Flask(__name__)

_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    # Sin SECRET_KEY estable cada worker de gunicorn firma con una clave distinta
    # y las sesiones (marca de "ya votó", login del admin) se pierden entre requests.
    print("WARNING: SECRET_KEY no configurada; usando clave aleatoria (no apto para producción)")
    _secret_key = secrets.token_hex(32)
app.config['SECRET_KEY'] = _secret_key
# Forzar el driver psycopg2: desde SQLAlchemy 2.1 "postgresql://" a secas elige psycopg 3,
# que no está instalado. Railway a veces entrega "postgres://", que SQLAlchemy 2 no acepta.
_db_url = os.environ.get('DATABASE_URL', '')
if _db_url.startswith('postgres://'):
    _db_url = 'postgresql://' + _db_url[len('postgres://'):]
if _db_url.startswith('postgresql://'):
    _db_url = 'postgresql+psycopg2://' + _db_url[len('postgresql://'):]
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# pool_pre_ping: si Postgres cerró una conexión ociosa, se reabre en vez de devolver un 500.
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'admin123')

# Cookie de sesión firmada: el cliente no puede leerla ni fabricarla.
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# En Railway (HTTPS) conviene SESSION_COOKIE_SECURE=1; en local con http debe quedar en 0.
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

db = SQLAlchemy(app)

# Template context processor
@app.context_processor
def utility_processor():
    def current_year():
        return datetime.now().year
    return dict(current_year=current_year)

# Models
class Competition(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    randomize_candidates = db.Column(db.Boolean, default=False)
    candidates = db.relationship('Candidate', backref='competition', lazy=True, cascade='all, delete-orphan')

class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id'), nullable=False)
    votes = db.relationship('Vote', backref='candidate', lazy=True, cascade='all, delete-orphan')

    def get_vote_count(self):
        return len(self.votes)

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate.id'), nullable=False)
    competition_id = db.Column(db.Integer, db.ForeignKey('competition.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Load candidates from txt file
def load_candidates_from_file(competition_slug):
    """Load candidates from a txt file (one candidate per line)"""
    filename = f'candidates_{competition_slug}.txt'
    if not os.path.exists(filename):
        return None

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            candidates = [line.strip() for line in f if line.strip()]
        return candidates
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return None

def sync_candidates_from_file(competition):
    """Sync candidates from txt file to database"""
    candidates_list = load_candidates_from_file(competition.slug)
    if candidates_list is None:
        return  # No file, skip sync

    # Get current candidates in DB
    current_candidates = {c.name: c for c in competition.candidates}
    file_candidates_set = set(candidates_list)

    # Remove candidates not in file
    for name, candidate in current_candidates.items():
        if name not in file_candidates_set:
            db.session.delete(candidate)
            print(f"Removed candidate: {name} from {competition.name}")

    # Add new candidates from file
    for name in candidates_list:
        if name not in current_candidates:
            new_candidate = Candidate(name=name, competition_id=competition.id)
            db.session.add(new_candidate)
            print(f"Added candidate: {name} to {competition.name}")

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error syncing candidates for {competition.name}: {e}")

# Initialize database
def init_db():
    with app.app_context():
        db.create_all()
        # Create competitions if they don't exist
        comp1 = Competition.query.filter_by(slug='3mt-uca').first()
        if not comp1:
            comp1 = Competition(name='3MT - UCA', slug='3mt-uca')
            db.session.add(comp1)

        comp2 = Competition.query.filter_by(slug='3min-uca-tfg').first()
        if not comp2:
            comp2 = Competition(name='3min - UCA TFG', slug='3min-uca-tfg')
            db.session.add(comp2)

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Database initialization warning: {e}")

        # Sync candidates from txt files if they exist
        comp1 = Competition.query.filter_by(slug='3mt-uca').first()
        comp2 = Competition.query.filter_by(slug='3min-uca-tfg').first()

        if comp1:
            sync_candidates_from_file(comp1)
        if comp2:
            sync_candidates_from_file(comp2)

init_db()

# Gunicorn corre con --preload: init_db() se ejecuta una sola vez en el proceso maestro
# (evita que N workers sincronicen candidatos a la vez y los dupliquen). Antes del fork
# hay que soltar las conexiones abiertas para que cada worker abra las suyas.
with app.app_context():
    db.engine.dispose()

# Session helpers
def is_admin():
    return session.get('admin') is True

def get_or_create_vote_token(slug):
    """Token por competencia guardado en la sesión firmada.

    Solo lo obtiene quien carga la página de votación con un cliente que
    conserva la cookie de sesión. Se consume al votar, así que cada token
    sirve para un único POST.
    """
    tokens = session.get('vote_tokens', {})
    if slug not in tokens:
        tokens[slug] = secrets.token_urlsafe(32)
        session['vote_tokens'] = tokens
        session.permanent = True
    return tokens[slug]

def consume_vote_token(slug, provided):
    tokens = session.get('vote_tokens', {})
    expected = tokens.get(slug)
    if not expected or not isinstance(provided, str) or not hmac.compare_digest(expected, provided):
        return False
    tokens.pop(slug, None)
    session['vote_tokens'] = tokens
    return True

def has_voted(slug):
    return slug in session.get('voted', [])

def mark_voted(slug):
    voted = list(session.get('voted', []))
    if slug not in voted:
        voted.append(slug)
    session['voted'] = voted
    session.permanent = True

# Routes
@app.route('/')
def index():
    if not is_admin():
        return redirect(url_for('index_login'))
    return render_template('index.html')

@app.route('/login')
def index_login():
    return render_template('index_login.html')

@app.route('/login/auth', methods=['POST'])
def index_auth():
    password = request.form.get('password') or ''
    if hmac.compare_digest(password, app.config['ADMIN_PASSWORD']):
        session['admin'] = True
        return redirect(url_for('index'))
    return render_template('index_login.html', error='Contraseña incorrecta')

@app.route('/vote/<slug>')
def vote_page(slug):
    competition = Competition.query.filter_by(slug=slug).first_or_404()

    already_voted = has_voted(slug)
    vote_token = None if already_voted else get_or_create_vote_token(slug)

    candidates = list(competition.candidates)
    if competition.randomize_candidates:
        random.shuffle(candidates)

    return render_template('vote.html',
                         competition=competition,
                         candidates=candidates,
                         has_voted=already_voted,
                         vote_token=vote_token)

@app.route('/api/vote/<slug>', methods=['POST'])
def submit_vote(slug):
    competition = Competition.query.filter_by(slug=slug).first_or_404()

    if has_voted(slug):
        return jsonify({'error': 'Ya has votado en esta competencia'}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Solicitud inválida'}), 400

    # El token solo existe en la sesión de quien cargó la página de votación.
    # Un POST directo sin sesión (curl, script) no lo tiene y se rechaza acá.
    if not consume_vote_token(slug, data.get('vote_token')):
        return jsonify({'error': 'Sesión de votación inválida. Recargá la página e intentá de nuevo.'}), 403

    candidate_ids = data.get('candidate_ids')
    if not candidate_ids or not isinstance(candidate_ids, list):
        return jsonify({'error': 'Candidatos no especificados'}), 400

    # Validate exactly 3 distinct candidates
    if not all(isinstance(cid, int) and not isinstance(cid, bool) for cid in candidate_ids):
        return jsonify({'error': 'Candidato inválido'}), 400
    if len(candidate_ids) != 3 or len(set(candidate_ids)) != 3:
        return jsonify({'error': 'Debes seleccionar exactamente 3 candidatos distintos'}), 400

    # Validate all candidates exist and belong to this competition
    for candidate_id in candidate_ids:
        candidate = Candidate.query.get(candidate_id)
        if not candidate or candidate.competition_id != competition.id:
            return jsonify({'error': 'Candidato inválido'}), 400

    # Record votes (all votes have equal weight)
    for candidate_id in candidate_ids:
        vote = Vote(candidate_id=candidate_id, competition_id=competition.id)
        db.session.add(vote)

    db.session.commit()

    mark_voted(slug)
    return jsonify({'success': True, 'message': '¡Gracias por votar!'})

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard_login.html')

@app.route('/dashboard/auth', methods=['POST'])
def dashboard_auth():
    password = request.form.get('password') or ''
    if hmac.compare_digest(password, app.config['ADMIN_PASSWORD']):
        session['admin'] = True
        return redirect(url_for('dashboard_main'))
    return render_template('dashboard_login.html', error='Contraseña incorrecta')

@app.route('/dashboard/main')
def dashboard_main():
    if not is_admin():
        return redirect(url_for('dashboard'))

    competitions = Competition.query.all()
    return render_template('dashboard.html', competitions=competitions)

@app.route('/api/dashboard/candidate', methods=['POST'])
def add_candidate():
    if not is_admin():
        return jsonify({'error': 'No autorizado'}), 401

    data = request.json
    candidate = Candidate(
        name=data['name'],
        competition_id=data['competition_id']
    )
    db.session.add(candidate)
    db.session.commit()

    return jsonify({'success': True, 'candidate': {
        'id': candidate.id,
        'name': candidate.name,
        'votes': 0
    }})

@app.route('/api/dashboard/candidate/<int:id>', methods=['DELETE'])
def delete_candidate(id):
    if not is_admin():
        return jsonify({'error': 'No autorizado'}), 401

    candidate = Candidate.query.get_or_404(id)
    db.session.delete(candidate)
    db.session.commit()

    return jsonify({'success': True})

@app.route('/api/dashboard/competition/<int:id>/randomize', methods=['POST'])
def toggle_randomize(id):
    if not is_admin():
        return jsonify({'error': 'No autorizado'}), 401

    competition = Competition.query.get_or_404(id)
    competition.randomize_candidates = not competition.randomize_candidates
    db.session.commit()

    return jsonify({'success': True, 'randomize': competition.randomize_candidates})

@app.route('/api/dashboard/stats/<int:competition_id>')
def get_stats(competition_id):
    if not is_admin():
        return jsonify({'error': 'No autorizado'}), 401

    competition = Competition.query.get_or_404(competition_id)
    candidates_with_votes = []

    for candidate in competition.candidates:
        candidates_with_votes.append({
            'id': candidate.id,
            'name': candidate.name,
            'votes': candidate.get_vote_count()
        })

    # Sort by votes descending
    candidates_with_votes.sort(key=lambda x: x['votes'], reverse=True)

    return jsonify({
        'competition': competition.name,
        'candidates': candidates_with_votes,
        'total_votes': sum(c['votes'] for c in candidates_with_votes)
    })

@app.route('/api/dashboard/competition/<int:id>/reset-votes', methods=['POST'])
def reset_votes(id):
    if not is_admin():
        return jsonify({'error': 'No autorizado'}), 401

    competition = Competition.query.get_or_404(id)

    # Delete all votes for this competition
    Vote.query.filter_by(competition_id=id).delete()
    db.session.commit()

    return jsonify({'success': True, 'message': 'Votos eliminados correctamente'})

@app.route('/dashboard/logout')
def logout():
    session.pop('admin', None)
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
