from flask import Flask, render_template, request, redirect, url_for, flash, session
import firebase_admin
from firebase_admin import credentials
from firebase_admin import db as firebase_db

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Initialize Firebase Admin SDK
cred = credentials.Certificate("/home/rgukt/my_flask_project/quizziz-2c051-firebase-adminsdk-5mpwp-98c1cc8ce1.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://quizziz-2c051-default-rtdb.firebaseio.com/'
})

# Routes

# Welcome Route
@app.route('/')
def welcome():
    return render_template('welcome.html')

# Signup Route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Store user credentials in Firebase
        users_ref = firebase_db.reference('users')
        users_ref.child(username).set({
            'username': username,
            'password': password
        })

        flash('Signup successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if user exists in Firebase
        user_ref = firebase_db.reference(f'users/{username}')
        user_data = user_ref.get()

        if user_data and user_data['password'] == password:
            session['logged_in'] = True
            session['username'] = username
            flash('Login successful!', 'success')
            return redirect(url_for('welcome'))
        else:
            flash('Invalid username or password. Please try again.', 'error')
    return render_template('login.html')

@app.route('/create_quiz', methods=['GET', 'POST'])
def create_quiz():
    if not session.get('logged_in'):
        return redirect(url_for('login'))  # Redirect to login if not logged in
    
    if request.method == 'POST':
        # Extract quiz data from the form
        quiz_name = request.form['quiz_name']
        timer = int(request.form['timer'])
        questions = request.form.getlist('questions[]')
        correct_options = [int(request.form[f'correct_options[{i}]']) for i in range(1, len(questions) + 1)]

        # Store quiz data in Firebase Realtime Database
        quiz_ref = firebase_db.reference('quizzes')
        new_quiz_ref = quiz_ref.push({
            'name': quiz_name,
            'timer': timer
        })
        quiz_id = new_quiz_ref.key

        # Store questions in Firebase Realtime Database
        questions_ref = firebase_db.reference(f'questions/{quiz_id}')
        for i, question in enumerate(questions):
            question_ref = questions_ref.push({
                'question': question
            })
            question_id = question_ref.key

            # Store options separately for each question
            options = request.form.getlist(f'options[{i}][]')
            options_ref = firebase_db.reference(f'options/{quiz_id}/{question_id}')
            for j, option_text in enumerate(options):
                is_correct = 1 if j == correct_options[i] else 0
                options_ref.push({
                    'option_text': option_text,
                    'is_correct': is_correct
                })

        flash('Quiz created successfully!', 'success')
        return redirect(url_for('create_quiz'))
    else:
        return render_template('create_quiz.html')


# Join Quiz Route
@app.route('/join_quiz', methods=['GET', 'POST'])
def join_quiz():
    if not session.get('logged_in'):
        return redirect(url_for('login'))  # Redirect to login if not logged in
    
    if request.method == 'POST':
        quiz_id = request.form.get('quiz_id')
        return redirect(url_for('join_specific_quiz', quiz_id=quiz_id))
    else:
        quizzes_ref = firebase_db.reference('quizzes')
        quizzes = quizzes_ref.get()
        if quizzes is not None:
            quizzes_list = [{'id': quiz_id, 'name': quiz_data['name'], 'duration': quiz_data['timer']} for quiz_id, quiz_data in quizzes.items()]
            return render_template('join_quiz.html', quizzes=quizzes_list)
        else:
            flash('No quizzes available.', 'error')
            return render_template('join_quiz.html', quizzes=[])

@app.route('/join_specific_quiz/<quiz_id>', methods=['GET', 'POST'])
def join_specific_quiz(quiz_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))  # Redirect to login if not logged in

    # Fetch quiz details from Firebase
    quiz_ref = firebase_db.reference(f'quizzes/{quiz_id}')
    quiz_data = quiz_ref.get()
    if quiz_data is None:
        flash('Quiz not found.', 'error')
        return redirect(url_for('join_quiz'))  # Redirect back to join quiz list

    quiz_name = quiz_data['name']
    duration = quiz_data['timer']

    # Fetch questions and options for the quiz from Firebase
    questions_ref = firebase_db.reference(f'questions/{quiz_id}')
    questions_data = questions_ref.get()

    # Check if questions exist
    if questions_data is None:
        flash('No questions available for this quiz.', 'error')
        return render_template('join_specific_quiz.html', quiz_name=quiz_name, duration=duration, quiz_details=[], options={})

    quiz_details = [{'question_id': key, 'question': value['question']} for key, value in questions_data.items()]

    options = {}
    for question_id, question_data in questions_data.items():
        options_ref = firebase_db.reference(f'options/{quiz_id}/{question_id}')
        options_data = options_ref.get()

        # Ensure that options are retrieved correctly
        options[question_id] = []  # Initialize empty list for options
        if options_data:
            options[question_id] = [{'text': option['option_text'], 'is_correct': option['is_correct']} for option in options_data.values()]

    return render_template('join_specific_quiz.html', quiz_name=quiz_name, duration=duration, quiz_details=quiz_details, options=options)


@app.route('/save_quiz_data', methods=['POST'])
def save_quiz_data():
    try:
        # Extract form data
        quiz_name = request.form['quiz_name']
        timer = int(request.form['timer'])
        questions = request.form.getlist('questions[]')
        options = [request.form.getlist(f'options[{question_id}][]') for question_id in questions]
        correct_options = [int(request.form[f'correct_options[{i}]']) for i in range(1, len(questions) + 1)]

        # Save quiz data to Firebase
        quiz_ref = firebase_db.reference('quizzes')
        new_quiz_ref = quiz_ref.push({
            'name': quiz_name,
            'timer': timer
        })
        quiz_id = new_quiz_ref.key

        for i, question in enumerate(questions):
            # Save question
            question_ref = firebase_db.reference(f'questions/{quiz_id}')
            new_question_ref = question_ref.push({'question': question})
            question_id = new_question_ref.key

            # Save options
            options_ref = firebase_db.reference(f'options/{quiz_id}/{question_id}')
            for j, option_text in enumerate(options[i]):
                options_ref.push({
                    'option_text': option_text
                })

            # Save correct option
            correct_option_ref = firebase_db.reference(f'correct_options/{quiz_id}/{question_id}')
            correct_option_ref.set(correct_options[i])

        flash('Quiz created successfully!', 'success')
        return redirect(url_for('create_quiz'))
    except Exception as e:
        flash(f'Error occurred: {str(e)}', 'error')
        return redirect(url_for('create_quiz'))


@app.route('/submit_quiz', methods=['POST'])
def submit_quiz():
    if not session.get('logged_in'):
        return redirect(url_for('login'))  # Redirect to login if not logged in
    
    try:
        quiz_data = session.get('quiz_data')
        total_questions = len(quiz_data)
        correct_answers = 0
        
        for question_id, user_answer in request.form.items():
            if user_answer == quiz_data[question_id]['correct_option']:
                correct_answers += 1
        
        # Calculate score percentage
        score = (correct_answers / total_questions) * 100
        
        return render_template('score.html', total_questions=total_questions, correct_answers=correct_answers, incorrect_answers=total_questions-correct_answers, score=score)
    
    except Exception as e:
        flash(f'Error occurred: {str(e)}', 'error')
        return redirect(url_for('welcome'))

if __name__ == '__main__':
    app.run(debug=True)

