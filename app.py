
import os
import base64
from datetime import date
from flask import Flask, render_template, request, redirect, session, flash, url_for, json
import mysql.connector
import requests
import pandas as pd
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor
import pymysql

app = Flask(__name__)

app.secret_key = os.urandom(24)

df = pd.read_excel('data.xlsx')


generic_name_column = 'Generic Name'
user_ratings_column = 'No of User Ratings'
price_column = 'Price'
medicines_column = 'List of Medicines'


# Create target variable on-the-fly for the entire dataset
df['Target_Score'] = df[user_ratings_column] / df[price_column]

# Initialize XGBoost model
model = XGBRegressor()

# Features and target variable for training
X_train, X_test, y_train, y_test = train_test_split(df[[user_ratings_column, price_column]], df['Target_Score'], test_size=0.2, random_state=42)

# Train the model
model.fit(X_train, y_train)

def get_best_brand(generic_name):
    # Filter data by generic name
    filtered_data = df[df[generic_name_column] == generic_name]

    if filtered_data.empty:
        return None, None, "No data available for the given generic name."

    # Feature engineering for filtered data
    features = filtered_data[[user_ratings_column, price_column]]

    # Make predictions on the filtered data
    predictions_filtered = model.predict(features)

    if not predictions_filtered.any():
        print("empty")
        return None, None, "No predictions available for the given generic name."

    # Find the medicine with the highest predicted target score
    best_brand_index = predictions_filtered.argmax()

    if best_brand_index >= len(filtered_data):
        return None, None, "Invalid index. Please check your data."

    best_brand_name = filtered_data.iloc[best_brand_index][medicines_column]
    best_brand_price = filtered_data.iloc[best_brand_index][price_column]

    return best_brand_name, best_brand_price, filtered_data


def get_symptoms_for_user(user_id):
    
    # Execute the SQL query to retrieve symptoms for the given user_id
    query = """
        SELECT s.symptom_name
        FROM user_symptoms us
        JOIN symptoms s ON us.symptom_id = s.symptom_id
        WHERE us.user_id = %s
        """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(query, (user_id,))
        results = cursor.fetchall()

    # Extract symptom names from the tuples and create a list
    symptom_names = [result[0] for result in results]
    return symptom_names

# Your existing functions go here...

# Update the 'add_user' route to insert previous symptoms and profile image
@app.route('/add_user', methods=['POST'])
def add_user():
    name = request.form.get('rname')
    username = request.form.get('rusername')
    dob = request.form.get('rdob')
    gender = request.form.get('rgender')
    password = request.form.get('rpassword')
    profile_image = request.files['profilePicture']  # Get the uploaded profile image
    symptoms = request.form.getlist('symptom')  # Get the selected symptoms as a list

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_details (username, dob, gender, password, profile_image) VALUES (%s, %s, %s, %s, %s)",
            (username, dob, gender, password, profile_image.read()))
        conn.commit()

        cursor.execute("SELECT * FROM user_details WHERE username = %s", (username,))
        myuser = cursor.fetchone()
        user_id = myuser[0]

        # Insert selected symptoms into a separate table
        for symptom_id in symptoms:
            cursor.execute("INSERT INTO user_symptoms (user_id, symptom_id) VALUES (%s, %s)", (user_id, symptom_id))
        conn.commit()

        #session['user_id'] = user_id

    return redirect('/login')






def is_human(captcha_response):
    secret="6LclNLooAAAAAL3e_lBcZ2h5hE-C2SnFGZgg226G"
    payload={'response':captcha_response,'secret':secret}
    response=requests.post('https://www.google.com/recaptcha/api/siteverify',payload)
    response_text=json.loads(response.text)
    return response_text['success']

def get_db():
    conn = mysql.connector.connect(
        port=3306,  # Change this to the appropriate port for your MySQL setup
        host="localhost",
        user="root",
        password="root",
        database="personal_details"
    )
    return conn



# ...
@app.route('/recommend_medicine', methods=['POST'])
def recommend_medicine():
    try:
        if 'user_id' in session:
            user_id = session['user_id']
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT username, dob, gender, profile_image FROM user_details WHERE user_id = %s", (user_id,))
                user_data = cursor.fetchone()
        
                if user_data:
                    username = user_data[0]
                    dob = user_data[1]
                    gender = user_data[2]
                    profile_image = user_data[3]

                    # Calculate age based on date of birth
                    today = date.today()
                    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

                    # Fetch the user's previous symptoms from the database
                    cursor.execute("SELECT s.symptom_name FROM symptoms s JOIN user_symptoms us ON s.symptom_id = us.symptom_id WHERE us.user_id = %s", (user_id,))
                    symptoms = [row[0] for row in cursor.fetchall()]

                    encoded_profile_image = base64.b64encode(profile_image).decode('utf-8')

                    
        
        if request.method == 'POST':
            symptom = request.form['symptom']
            severity = request.form['severity']

            # Connect to the database
            connection = get_db()

            # Query the database for recommended medicine based on the symptom and severity
            cursor = connection.cursor()
            sefects=get_symptoms_for_user(user_id)
            print(sefects)
            cursor.execute('''
        SELECT recommended_medicine_generic_name
        FROM medicine_recommendation
        WHERE symptom = %s
        AND severity = %s
        AND minimum_age < %s < maximum_age
        AND recommended_medicine_generic_name NOT IN (
            SELECT recommended_medicine_generic_name
            FROM medicine_recommendation
            WHERE symptom = %s
            AND severity = %s
            AND minimum_age < %s < maximum_age
            AND side_effects LIKE %s
        )
    ''', (symptom, severity, age, symptom, severity, age, '%' + ','.join(sefects) + '%'))

            recommended_medicine = cursor.fetchone()
            print(cursor.statement)  # Print the full SQL statement
            rc=str(recommended_medicine)
            sol1,sol2,sol3=get_best_brand(rc[2:-3])
            subset_data = sol3[['List of Medicines', 'Price']]
            # Convert the subset of DataFrame to a list
            medicine = subset_data.values.tolist()
            # Close the database connection
            #side_effects
            cursor.execute('''
        SELECT Contraindications
        FROM medicine_recommendation
        WHERE recommended_medicine_generic_name = %s
    ''', (rc[2:-3],))

            side_effects = cursor.fetchone()
            connection.close()
            if recommended_medicine:
                print(side_effects)
                return render_template('recommended_medicine.html', recommended_medicine=sol1,price=sol2,all_medicines=medicine,side_effects=side_effects,gname=rc[2:-3])
    except Exception as e:
        return render_template('no_recommendation_found.html')

@app.route('/profile')
def profile():
    age = None
    if 'user_id' in session:
        user_id = session['user_id']
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT username, dob, gender, profile_image FROM user_details WHERE user_id = %s", (user_id,))
            user_data = cursor.fetchone()

            if user_data:
                username = user_data[0]
                dob = user_data[1]
                gender = user_data[2]
                profile_image = user_data[3]

                # Calculate age based on date of birth
                today = date.today()
                age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

                # Fetch the user's previous symptoms from the database
                cursor.execute("SELECT s.symptom_name FROM symptoms s JOIN user_symptoms us ON s.symptom_id = us.symptom_id WHERE us.user_id = %s", (user_id,))
                symptoms = [row[0] for row in cursor.fetchall()]

                encoded_profile_image = base64.b64encode(profile_image).decode('utf-8')


                return render_template('profile.html', username=username, age=age, gender=gender, profile_image=encoded_profile_image, symptoms=symptoms)
            else:
                return "User data not found."
    else:
        return redirect('/login')


# @app.route('/')
# def index():
#     return render_template('index.html')


@app.route('/')
def home():
    if 'user_id' in session:
        return redirect('/symptoms')
    return render_template('index.html')

@app.route('/login')
def login():
    if 'user_id' in session:
        return redirect('/symptoms')
    return render_template('login.html')

@app.route('/enter_symptoms')
def enter_symptoms():
    return "..."

@app.route('/register')
def register():
    if 'user_id' in session:
        return redirect('/symptoms')
    return render_template('register.html')

@app.route('/symptoms')
def symptoms():
    if 'user_id' in session:
        return render_template('symptoms.html')
    else:
        return redirect('/login')


@app.route('/login_validation', methods=['POST'])
def login_validation():
    sitekey="6LclNLooAAAAAH589aoyKTKyLmLEaMIY8KFiKrUe"
    if request.method=="POST":
        username = request.form.get('username')
        password = request.form.get('password')
        captcha_response=request.form['g-recaptcha-response']
        if is_human(captcha_response):
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM user_details WHERE username = %s AND password = %s", (username, password))
                user = cursor.fetchone()

            if user:
            
                session['user_id'] = user[0]
                
                return redirect('/symptoms')
            else:
                return redirect('/login')
        else:
            return redirect('/login')




@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect('/login')

if __name__ == "__main__":
    app.run(debug=True)
