import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'admin123')

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

# Routes
@app.route('/')
def index():
    if request.cookies.get('admin_auth') != app.config['ADMIN_PASSWORD']:
        return redirect(url_for('index_login'))
    return render_template('index.html')

@app.route('/login')
def index_login():
    return render_template('index_login.html')

@app.route('/login/auth', methods=['POST'])
def index_auth():
    password = request.form.get('password')
    if password == app.config['ADMIN_PASSWORD']:
        response = make_response(redirect(url_for('index')))
        response.set_cookie('admin_auth', app.config['ADMIN_PASSWORD'], max_age=24*60*60)
        return response
    return render_template('index_login.html', error='Contraseña incorrecta')

@app.route('/vote/<slug>')
def vote_page(slug):
    competition = Competition.query.filter_by(slug=slug).first_or_404()

    # Check if already voted
    cookie_name = f'voted_{slug}'
    has_voted = request.cookies.get(cookie_name)

    candidates = list(competition.candidates)
    if competition.randomize_candidates:
        random.shuffle(candidates)

    return render_template('vote.html',
                         competition=competition,
                         candidates=candidates,
                         has_voted=has_voted)

@app.route('/api/vote/<slug>', methods=['POST'])
def submit_vote(slug):
    competition = Competition.query.filter_by(slug=slug).first_or_404()

    # Check if already voted
    cookie_name = f'voted_{slug}'
    if request.cookies.get(cookie_name):
        return jsonify({'error': 'Ya has votado en esta competencia'}), 400

    candidate_ids = request.json.get('candidate_ids')
    if not candidate_ids or not isinstance(candidate_ids, list):
        return jsonify({'error': 'Candidatos no especificados'}), 400

    # Validate exactly 3 candidates
    if len(candidate_ids) != 3:
        return jsonify({'error': 'Debes seleccionar exactamente 3 candidatos'}), 400

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

    # Set cookie
    response = make_response(jsonify({'success': True, 'message': '¡Gracias por votar!'}))
    response.set_cookie(cookie_name, 'true', max_age=365*24*60*60)  # 1 year

    return response

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard_login.html')

@app.route('/dashboard/auth', methods=['POST'])
def dashboard_auth():
    password = request.form.get('password')
    if password == app.config['ADMIN_PASSWORD']:
        response = make_response(redirect(url_for('dashboard_main')))
        response.set_cookie('admin_auth', app.config['ADMIN_PASSWORD'], max_age=24*60*60)
        return response
    return render_template('dashboard_login.html', error='Contraseña incorrecta')

@app.route('/dashboard/main')
def dashboard_main():
    if request.cookies.get('admin_auth') != app.config['ADMIN_PASSWORD']:
        return redirect(url_for('dashboard'))

    competitions = Competition.query.all()
    return render_template('dashboard.html', competitions=competitions)

@app.route('/api/dashboard/candidate', methods=['POST'])
def add_candidate():
    if request.cookies.get('admin_auth') != app.config['ADMIN_PASSWORD']:
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
    if request.cookies.get('admin_auth') != app.config['ADMIN_PASSWORD']:
        return jsonify({'error': 'No autorizado'}), 401

    candidate = Candidate.query.get_or_404(id)
    db.session.delete(candidate)
    db.session.commit()

    return jsonify({'success': True})

@app.route('/api/dashboard/competition/<int:id>/randomize', methods=['POST'])
def toggle_randomize(id):
    if request.cookies.get('admin_auth') != app.config['ADMIN_PASSWORD']:
        return jsonify({'error': 'No autorizado'}), 401

    competition = Competition.query.get_or_404(id)
    competition.randomize_candidates = not competition.randomize_candidates
    db.session.commit()

    return jsonify({'success': True, 'randomize': competition.randomize_candidates})

@app.route('/api/dashboard/stats/<int:competition_id>')
def get_stats(competition_id):
    if request.cookies.get('admin_auth') != app.config['ADMIN_PASSWORD']:
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
    if request.cookies.get('admin_auth') != app.config['ADMIN_PASSWORD']:
        return jsonify({'error': 'No autorizado'}), 401

    competition = Competition.query.get_or_404(id)

    # Delete all votes for this competition
    Vote.query.filter_by(competition_id=id).delete()
    db.session.commit()

    return jsonify({'success': True, 'message': 'Votos eliminados correctamente'})

@app.route('/dashboard/logout')
def logout():
    response = make_response(redirect(url_for('dashboard')))
    response.set_cookie('admin_auth', '', max_age=0)
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
