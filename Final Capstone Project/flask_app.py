from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import firebase_admin
from firebase_admin import credentials, db as firebase_db, firestore, storage
from flask_bcrypt import Bcrypt
from uuid import uuid4
import logging

app = Flask(__name__)
app.secret_key = 'your_secret_key'
bcrypt = Bcrypt(app)

# Load the Firebase credentials
firebase_credentials_path ="C:\\Users\\HOME\\Desktop\\my_flask_project\\quizziz-2c051-firebase-adminsdk-5mpwp-1a3a7cb7ee.json"
cred = credentials.Certificate(firebase_credentials_path)
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://quizziz-2c051-default-rtdb.firebaseio.com/',
    'storageBucket': 'quizziz-2c051.appspot.com'
})

# Create a Firestore client
db = firestore.client()

# Set up logging
logging.basicConfig(level=logging.INFO)

@app.route('/')
def welcome():
    return render_template('welcome.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # Check if the username already exists
        users_ref = db.collection('users')
        query = users_ref.where('username', '==', username).stream()
        if any(query):
            flash('Username already exists. Please choose a different one.', 'error')
            return redirect(url_for('signup'))

        try:
            # Store the new user in Firestore
            users_ref.add({
                'username': username,
                'password': hashed_password
            })
            flash('Signup successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error occurred: {str(e)}', 'error')
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        app.logger.info(f'Received login attempt for username: {username}')

        # Retrieve user from Firestore
        users_ref = db.collection('users')
        query = users_ref.where('username', '==', username).stream()
        user = None
        for doc in query:
            user = doc.to_dict()
            break

        if user:
            app.logger.info(f'User found for username: {username}')
            if bcrypt.check_password_hash(user['password'], password):
                session['logged_in'] = True
                session['username'] = username
                app.logger.info(f'User {username} logged in successfully.')
                return redirect(url_for('enter'))
            else:
                app.logger.warning(f'Invalid password for username: {username}')
        else:
            app.logger.warning(f'User not found for username: {username}')

        flash('Invalid username or password', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/enter')
def enter():
    if not session.get('logged_in'):
        logging.info("User not logged in, redirecting to login")
        return redirect(url_for('login'))
    logging.info(f"User {session['username']} entered the page")
    return render_template('enter.html')

@app.route('/create_quiz', methods=['GET', 'POST'])
def create_quiz():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        quiz_name = request.form['quiz_name']
        timer = int(request.form['timer'])
        questions = request.form.getlist('questions[]')
        correct_options = request.form.getlist('correct_options[]')

        # Handle file uploads
        images = request.files.getlist('images[]')

        try:
            # Save quiz data in Firebase Realtime Database
            quiz_ref = firebase_db.reference('quizzes').push({
                'name': quiz_name,
                'timer': timer
            })
            quiz_id = quiz_ref.key

            questions_ref = quiz_ref.child('questions')
            for i, question in enumerate(questions):
                question_ref = questions_ref.push({
                    'question': question
                })
                question_id = question_ref.key

                # Handle image upload for the question
                image_url = None
                if i < len(images):
                    image = images[i]
                    if image:
                        filename = secure_filename(image.filename)
                        blob = storage.bucket().blob(f'quiz_images/{quiz_id}/{question_id}/{filename}')
                        blob.upload_from_file(image)
                        image_url = blob.public_url
                        question_ref.update({
                            'image_url': image_url
                        })

                # Store options for the question
                options = request.form.getlist(f'options[{i}][]')
                correct_option_text = correct_options[i].strip()

                options_ref = question_ref.child('options')
                correct_option_id = None
                for option_text in options:
                    option_id = str(uuid4())

                    # Normalize option text for comparison
                    normalized_option_text = option_text.strip().lower()
                    normalized_correct_option_text = correct_option_text.lower()

                    is_correct = normalized_option_text == normalized_correct_option_text

                    options_ref.child(option_id).set({
                        'option_text': option_text,
                        'is_correct': is_correct
                    })

                    if is_correct:
                        correct_option_id = option_id

                # Update correct_option_id at the end of options node
                if correct_option_id:
                    question_ref.update({'correct_option': correct_option_id})
                else:
                    logging.warning(f"Correct option ID not set for question ID {question_id}")

            flash('Quiz created successfully!', 'success')
            return redirect(url_for('create_quiz'))
        except Exception as e:
            logging.error(f"Error during quiz creation: {e}")
            flash(f'Error occurred: {str(e)}', 'error')
            return redirect(url_for('create_quiz'))
    else:
        return render_template('create_quiz.html')


@app.route('/join_quiz', methods=['GET', 'POST'])
def join_quiz():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        quiz_id = request.form.get('quiz_id')
        return redirect(url_for('join_specific_quiz', quiz_id=quiz_id))
    else:
        try:
            quizzes_ref = firebase_db.reference('quizzes')
            quizzes = quizzes_ref.get()
            if quizzes:
                quizzes_list = []
                for quiz_id, quiz_data in quizzes.items():
                    name = quiz_data.get('name', f'Quiz {quiz_id}')
                    duration = quiz_data.get('timer', 'Unknown')
                    quizzes_list.append({'id': quiz_id, 'name': name, 'duration': duration})
                return render_template('join_quiz.html', quizzes=quizzes_list)
            else:
                flash('No quizzes available.', 'error')
                return render_template('join_quiz.html', quizzes=[])
        except Exception as e:
            logging.error(f"Error fetching quizzes: {e}")
            flash(f'Error occurred: {str(e)}', 'error')
            return render_template('join_quiz.html', quizzes=[])


@app.route('/join_specific_quiz/<quiz_id>', methods=['GET', 'POST'])
def join_specific_quiz(quiz_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    try:
        # Fetch quiz details from Firebase
        quiz_ref = firebase_db.reference(f'quizzes/{quiz_id}')
        quiz_data = quiz_ref.get()
        if not quiz_data:
            flash('Quiz not found.', 'error')
            return redirect(url_for('join_quiz'))

        quiz_name = quiz_data['name']
        duration = quiz_data['timer']

        # Fetch questions and options for the quiz from Firebase
        questions_ref = firebase_db.reference(f'quizzes/{quiz_id}/questions')
        questions_data = questions_ref.get()

        if not questions_data:
            flash('No questions available for this quiz.', 'error')
            return render_template('join_specific_quiz.html', quiz_name=quiz_name, duration=duration, quiz_details=[], options={})

        quiz_details = []
        options = {}

        for question_id, question_data in questions_data.items():
            question_text = question_data['question']
            image_url = question_data.get('image_url')

            quiz_details.append({
                'question_id': question_id,
                'question': question_text,
                'image_url': image_url
            })

            options_ref = firebase_db.reference(f'quizzes/{quiz_id}/questions/{question_id}/options')
            options_data = options_ref.get()

            options[question_id] = []
            if options_data:
                for option_id, option in options_data.items():
                    options[question_id].append({'id': option_id, 'text': option['option_text']})

        if request.method == 'POST':
            correct_answers = 0
            total_questions = len(questions_data)

            for question_id, question_data in questions_data.items():
                correct_option = question_data.get('correct_option')
                selected_option = request.form.get(question_id)

                if selected_option == correct_option:
                    correct_answers += 1

            score = (correct_answers / total_questions) * 100

            # Store score details in session
            session['total_questions'] = total_questions
            session['correct_answers'] = correct_answers
            session['incorrect_answers'] = total_questions - correct_answers

            flash(f'You scored {score}%', 'success')
            return redirect(url_for('score'))

        return render_template('join_specific_quiz.html', quiz_name=quiz_name, duration=duration, quiz_details=quiz_details, options=options)
    except Exception as e:
        logging.error(f"Error joining specific quiz: {e}")
        flash(f'Error occurred: {str(e)}', 'error')
        return redirect(url_for('join_quiz'))


@app.route('/submit_quiz', methods=['POST'])
def submit_quiz():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    try:
        data = request.get_json()
        app.logger.debug('Received data: %s', data)
        quiz_id = data.get('quiz_id')
        username = data.get('username')
        total_questions = data.get('total_questions')
        correct_answers = data.get('correct_answers')
        incorrect_answers = data.get('incorrect_answers')
        user_answers = data.get('user_answers')

        if not quiz_id or not username:
            return 'Quiz ID or Username is missing.', 400

        # Store user answers and scores in Firebase
        user_answers_ref = firebase_db.reference(f'user_answers/{quiz_id}/{username}')
        user_answers_ref.set(user_answers)

        user_scores_ref = firebase_db.reference(f'user_scores/{quiz_id}/{username}')
        user_scores_ref.set({
            'correct_answers': correct_answers,
            'incorrect_answers': incorrect_answers,
            'total_questions': total_questions
        })

        return '', 204
    except Exception as e:
        app.logger.error('Error occurred: %s', str(e))
        return str(e), 500


@app.route('/score')
def score():
    # Retrieve the score data from the session
    total_questions = session.get('total_questions', 0)
    correct_answers = session.get('correct_answers', 0)
    incorrect_answers = session.get('incorrect_answers', 0)

    return render_template('score.html', total_questions=total_questions, correct_answers=correct_answers, incorrect_answers=incorrect_answers)

@app.route('/quizz_contact')
def quizz_contact():
    return render_template('quizz_contact.html')


if __name__ == '__main__':
    app.run(debug=True)
