from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_mail import Mail, Message
import random
import string
from datetime import datetime, timedelta
import mysql.connector
from retrying import retry
from flask import session
from flask import g 
from dotenv import load_dotenv
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'
load_dotenv()
# Configure email settings
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')  

mail = Mail(app)

def get_db():
    if 'db' not in g:
        g.db = mysql.connector.connect(user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'), host=os.getenv('DB_HOST'), database=os.getenv('DB_NAME'))

    return g.db
def get_cursor():
    return get_db().cursor()

# Home page route
@app.route('/')
def home():
    return redirect(url_for('login'))

# Login page route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            # Establish a new database connection and cursor
            cnx = get_db()
            cursor = get_cursor()

            username_email = request.form['email']
            password = request.form['password']
            # Query to check username/email and password
            query = "SELECT * FROM users WHERE (username = %s OR email = %s) AND password = %s"
            # Execute the query
            cursor.execute(query, (username_email, username_email, password))
            # Fetch the user
            user = cursor.fetchone()
            print("User:", user)  # Print user for debugging
            if user:
                # Update last_login timestamp
                update_query = "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = %s"
                cursor.execute(update_query, (user[0],))  # Accessing user_id by index
                cnx.commit()  # Commit the transaction

                print("Last login timestamp updated successfully")
                # Redirect to home page
                print("Redirecting to main page")  # Print statement for debugging
                # Store user information in session
                session['user_id'] = user[0]
                session['username'] = user[1]
                session['email'] = user[2]
                print("Session after login:", session)
                # Print session data
                return redirect(url_for('main_page'))

            else:
                flash("Invalid username/email or password", "error")
        except Exception as e:
            print("Error during login:", e)
            flash("An error occurred during login. Please try again later.", "error")
        finally:
            # Close the cursor
            if cursor:
                cursor.close()

    # Render the login template for GET requests
    return render_template('login.html')

# Main page route
@app.route('/main_page')
def main_page():
    try:
        # Check if user is logged in
        if 'user_id' not in session:
            flash("Please login to access this page", "error")
            return redirect(url_for('login'))

        # Retrieve user information from session
        user_id = session.get('user_id')
        username = session.get('username')
        email = session.get('email')

        if not (user_id and username and email):
            print("Session data incomplete. Redirecting to login page.")
            flash("Session data incomplete. Please login again.", "error")
            return redirect(url_for('login'))

        # Create a dictionary containing user information
        user = {
            'user_id': user_id,
            'username': username,
            'email': email
        }

        # Define the movie_in_watchlist function
        def movie_in_watchlist(movie_id):
            try:
                # Establish a new database connection and cursor
                cnx = get_db()
                cursor = cnx.cursor()

                # Query to check if the movie is in the user's watchlist
                watchlist_query = "SELECT * FROM watchlist WHERE user_id = %s AND movie_id = %s"
                cursor.execute(watchlist_query, (user_id, movie_id))
                return cursor.fetchone() is not None
            except Exception as e:
                print("Error checking watchlist:", e)
                return False
            finally:
                # Close the cursor
                if 'cursor' in locals() and cursor:
                    cursor.close()

        # Query to fetch recent movies from the database
        query = "SELECT DISTINCT m.*, cr.average_rating FROM movies m LEFT JOIN cumulative_ratings cr ON m.movie_id = cr.movie_id ORDER BY m.release_year DESC LIMIT 8"

        # Establish a new database connection and cursor
        cnx = get_db()
        cursor = cnx.cursor()

        # Execute the query
        cursor.execute(query)

        # Fetch all recent movies
        recent_movies = cursor.fetchall()

        update_cumulative_ratings()

        # Pass the recent movies data, user information, and movie_in_watchlist function to the template
        return render_template('main_page.html', user=user, recent_movies=recent_movies, movie_in_watchlist=movie_in_watchlist)

    except Exception as e:
        print("Error in main_page route:", e)
        flash("An error occurred while loading the main page. Please try again later.", "error")
        return redirect(url_for('login'))  # Redirect to a default route in case of error
    finally:
        # Close the cursor if it's not None
        if 'cursor' in locals() and cursor:
            cursor.close()


def update_cumulative_ratings():
    try:
        # Connect to the database
        connection = mysql.connector.connect(host="Monesha", user="Monesha", password="SriRam33Lak$", database="movie_review_sys")

        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO cumulative_ratings (movie_id, average_rating, number_of_ratings)
            SELECT pr.movie_id, AVG(pr.personal_rating_value), COUNT(*)
            FROM personal_ratings pr
            GROUP BY pr.movie_id
            ON DUPLICATE KEY UPDATE
            average_rating = VALUES(average_rating),
            number_of_ratings = VALUES(number_of_ratings)
        """)
        cursor.execute("""
            UPDATE cumulative_ratings cr
            JOIN (
                SELECT movie_id, COUNT(*) AS new_num_ratings
                FROM personal_ratings
                GROUP BY movie_id
            ) AS new_ratings ON cr.movie_id = new_ratings.movie_id
            SET cr.number_of_ratings = new_ratings.new_num_ratings
        """)

        connection.commit()
        print("Cumulative ratings updated successfully")
    except mysql.connector.Error as e:
        print("Error updating cumulative ratings:", e)
        connection.rollback()
    finally:
        cursor.close()
        connection.close()

# New route for movie search
@app.route('/search')
def search_movies():
    try:
        # Receive the query parameter 'q' from the request URL
        query = request.args.get('q')

        if query:  # Check if query parameter is provided
            # Query the database for movie names that match the input value
            search_query = "SELECT movie_id, title FROM movies WHERE title LIKE %s"
            cursor = get_cursor()
            cursor.execute(search_query, (f'%{query}%',))
            matching_movies = cursor.fetchall()

            # Return matching movie titles and IDs as JSON data
            return jsonify(matching_movies)
        else:
            # Handle case where query parameter is not provided
            return jsonify({"message": "No search query provided."}), 400
    except Exception as e:
        # Handle exceptions, such as database connection errors or SQL syntax errors
        return jsonify({"error": str(e)}), 500
    finally:
        # Close cursor
        if cursor:
            cursor.close()

from datetime import datetime

@app.route('/movie/<int:movie_id>', methods=['GET', 'POST'])
def movie_details(movie_id):
    try:
        if 'user_id' in session:
            # Retrieve user information from the session
            user_id = session.get('user_id')
            username = session.get('username')

            user = {
                'id': user_id,
                'username': username,  
            }

        if request.method == 'POST':
            try:
                # Retrieve review text and star rating from form data
                review_text = request.form.get('review_text')
                star_rating = request.form.get('star_rating')
                current_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                if star_rating is not None:
                    star_rating = int(star_rating)  # Convert to integer if present
                cursor = get_cursor()
                # Store the review text and submission datetime in the 'reviews' table
                cursor.execute("INSERT INTO reviews (user_id, movie_id, review_text, submission_datetime) VALUES (%s, %s, %s, %s)",
                            (session['user_id'], movie_id, review_text, current_datetime))
                get_db().commit()

                # Store the star rating and submission datetime in the 'personal_ratings' table
                cursor.execute("INSERT INTO personal_ratings (user_id, movie_id, personal_rating_value, submission_datetime) VALUES (%s, %s, %s, %s)",
                            (session['user_id'], movie_id, star_rating, current_datetime))
                get_db().commit()

                # Redirect to the same movie details page to avoid form resubmission
                return redirect(url_for('movie_details', movie_id=movie_id))
            except Exception as e:
                print("Error while adding review and rating:", e)
                flash("An error occurred while adding review and rating. Please try again.", "error")
            finally:
                # Close cursor
                if cursor:
                    cursor.close()

        # Fetch movie details from the database
        movie_details = get_movie_details(movie_id)
        movie_reviews = get_movie_reviews(movie_id)
        # Check if user is logged in and retrieve user information
        if movie_reviews is None:
            movie_reviews = [] 
        return render_template('movie_details.html', movie_details=movie_details, user=user, movie_reviews=movie_reviews)
    except Exception as e:
        print("Error in movie_details route:", e)
        flash("An error occurred while loading movie details. Please try again later.", "error")


# Function to retrieve movie reviews from the database
# Function to retrieve movie reviews from the database
def get_movie_reviews(movie_id):
    try:
        # Establish a new database connection
        cnx = establish_connection()
        if cnx:
            # Create a cursor object within a context manager
            with cnx.cursor() as cursor:
                # Query to fetch distinct reviews for the specified movie
                query = """
                    SELECT DISTINCT r.review_text, pr.personal_rating_value, u.username
                    FROM reviews r
                    LEFT JOIN personal_ratings pr ON r.user_id = pr.user_id AND r.movie_id = pr.movie_id
                    JOIN users u ON r.user_id = u.user_id
                    WHERE r.movie_id = %s AND r.review_text IS NOT NULL
                    AND r.submission_datetime = pr.submission_datetime
                """

                # Execute the query with the movie_id parameter
                cursor.execute(query, (movie_id,))

                # Fetch the distinct reviews
                reviews = cursor.fetchall()

                return reviews  # Return the fetched reviews

    except Exception as e:
        print("Error fetching movie reviews:", e)
        return None  # Return None in case of any error

    finally:
        # Close the connection in the finally block to ensure it's always closed
        if cnx:
            cnx.close()



# Function to retrieve movie details from the database
def get_movie_details(movie_id):
    try:
        # Establish a new database connection
        cnx = establish_connection()
        if cnx:
            # Create a cursor object
            cursor = cnx.cursor()

            # Query to fetch movie details from the database
            query = "SELECT m.movie_id, m.title, m.poster_url, m.release_year, m.plot, m.genre, m.cast, m.age_rating, m.runtime, m.metascore, AVG(pr.personal_rating_value) AS avg_rating FROM movies m LEFT JOIN personal_ratings pr ON m.movie_id = pr.movie_id WHERE m.movie_id = %s"

            # Execute the query with the movie_id parameter
            cursor.execute(query, (movie_id,))

            # Fetch the movie details
            movie_details = cursor.fetchone()

            # Check if movie details are found
            if movie_details:
                # Create a dictionary to store the movie details
                movie_dict = {
                    "id": movie_details[0],
                    "title": movie_details[1],
                    "poster_url": movie_details[2],
                    "release_year": movie_details[3],
                    "plot": movie_details[4],
                    "genre": movie_details[5],
                    "cast": movie_details[6],
                    "age_rating": movie_details[7],
                    "runtime": movie_details[8],
                    "metascore": movie_details[9],
                    "avg_rating": movie_details[10]
                }
                return movie_dict
            else:
                return None  # Return None if movie details are not found

    except Exception as e:
        print("Error fetching movie details:", e)
        return None  # Return None in case of any error

    finally:
        # Close the cursor and connection
        if cursor:
            cursor.close()
        if cnx:
            cnx.close()

# Route to add review and rating
@app.route('/movie/<int:movie_id>', methods=['POST'])
def add_review_and_rating(movie_id):
    if 'user_id' in session:
        user_id = session['user_id']
        if request.method == 'POST':
            review_text = request.form.get('review_text')
            star_rating = request.form.get('star_rating')
            if star_rating is not None:
                star_rating = int(star_rating)
            cursor = get_cursor() 
            cursor.execute("INSERT INTO reviews (user_id, movie_id, review_text) VALUES (%s, %s, %s)", (user_id, movie_id, review_text))
            get_db().commit()
            cursor.execute("INSERT INTO personal_ratings (user_id, movie_id, personal_rating_value) VALUES (%s, %s, %s)", (user_id, movie_id, star_rating))
            get_db().commit()
            
            return redirect(url_for('movie_details', movie_id=movie_id))
    else:
        flash("Please login to add reviews and ratings", "error")
        return redirect(url_for('login'))

# My Account route
@app.route('/my_account')
def my_account():
    try:
        # Check if user is logged in
        if 'user_id' in session:
            # Retrieve user information from session
            user_id = session.get('user_id')
            username = session.get('username')
            email = session.get('email')
            
            # Retrieve date_registered from database
            cursor = get_cursor()
            cursor.execute("SELECT date_registered FROM users WHERE user_id = %s", (user_id,))
            date_registered = cursor.fetchone()[0]  # Assuming date_registered is the first column
            
            if user_id and username and email:
                # Create a dictionary containing user information
                user = {
                    'user_id': user_id,
                    'username': username,
                    'email': email,
                    'date_registered': date_registered  # Add date_registered to user dictionary
                }

                # Render the my_account.html template with user information
                return render_template('my_account.html', user=user)
        else:
            # If user is not logged in, redirect to the login page
            flash("Please login to view your account", "error")
            return redirect(url_for('login'))
    except Exception as e:
        print("Error in my_account route:", e)
        flash("An error occurred while loading your account information. Please try again later.", "error")


# New route to display user's reviews
# New route to display user's reviews
@app.route('/my_reviews')
def my_reviews():
    try:
        # Check if user is logged in
        if 'user_id' in session:
            # Retrieve user information from session
            user_id = session.get('user_id')
            username = session.get('username')

            if user_id and username:
                # Create a dictionary containing user information
                user = {
                    'user_id': user_id,
                    'username': username
                }

                # Query to fetch user's reviews
                query = """
                    SELECT m.poster_url, m.title, pr.personal_rating_value AS rating, r.review_text, r.submission_datetime
                    FROM movies m
                    JOIN reviews r ON m.movie_id = r.movie_id
                    JOIN personal_ratings pr ON r.movie_id = pr.movie_id AND r.user_id = pr.user_id
                    WHERE r.user_id = %s
                    AND r.submission_datetime = pr.submission_datetime 
                    ORDER BY r.submission_datetime DESC;

                """
                cursor = get_cursor()
                cursor.execute(query, (user_id,))
                reviews = cursor.fetchall()

                # Pass the user and user_reviews data to the template
                return render_template('my_reviews.html', user=user, reviews=reviews)

        # If user is not logged in or user information is incomplete, redirect to login
        flash("Please login to access this page", "error")
        return redirect(url_for('login'))
    except Exception as e:
        print("Error in my_reviews route:", e)
        flash("An error occurred while loading your reviews. Please try again later.", "error")
    # Add a default return statement outside of the try block
    return redirect(url_for('login'))  # or any other appropriate response


# Route to display the user's watchlist
@app.route('/watchlist')
def watchlist():
    try:
        if 'user_id' in session:
            user_id = session.get('user_id')
            username = session.get('username')

            user = {
                'id': user_id,
                'username': username,  
            }

            query = "SELECT  w.title, m.poster_url FROM watchlist w JOIN movies m ON w.movie_id = m.movie_id WHERE w.user_id = %s"

            cursor = get_cursor()
            cursor.execute(query, (user_id,))
            watchlist_movies = cursor.fetchall()

            # Pass movie_id along with other variables to the template
            return render_template('watchlist.html', watchlist_movies=watchlist_movies, user=user)
        else:
            flash("Please login to access this page", "error")
            return redirect(url_for('login'))
    except Exception as e:
        print("Error in watchlist route:", e)
        flash("An error occurred while loading your watchlist. Please try again later.", "error")

# Sign up page route
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    try:
        if request.method == 'POST':
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            if len(password) > 10 or not any(char in string.punctuation for char in password):
                flash("Password must be at most 10 characters long and contain at least one special character", "error")
            else:
                query = "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)"
                cursor = get_cursor()
                cursor.execute(query, (username, email, password))
                get_db().commit()
                flash("Sign up successful! Please log in.", "success")
                return redirect(url_for('login'))
        return render_template('signup.html')
    except Exception as e:
        print("Error in signup route:", e)
        flash("An error occurred during sign up. Please try again later.", "error")
# Forgot password page route
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    try:
        if request.method == 'POST':
            email = request.form['email']
            query = "SELECT * FROM users WHERE email = %s"
            cursor = get_cursor()
            cursor.execute(query, (email,))
            user = cursor.fetchone()
            if user:
                reset_token = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
                query = "UPDATE users SET reset_token = %s, reset_token_expiry = %s WHERE email = %s"
                cursor.execute(query, (reset_token, datetime.now() + timedelta(minutes=10), email))
                get_db().commit()
                flash("Reset token sent to your email.", "success")
                # Send reset token to email
                send_email(email, reset_token)  # Pass email and reset_token to the send_email function
                return redirect(url_for('reset_password'))
            else:
                flash("Email not found", "error")
        return render_template('forgot_password.html')
    except Exception as e:
        print("Error in forgot_password route:", e)
        flash("An error occurred during password reset. Please try again later.", "error")

# Reset password page route
@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    cursor = None  # Initialize cursor variable
    try:
        if request.method == 'POST':
            email = request.form['email']
            reset_token = request.form['reset_token']
            new_password = request.form['new_password']
            query = "SELECT * FROM users WHERE email = %s AND reset_token = %s AND reset_token_expiry > %s"
            
            cursor = get_cursor()
            cursor.execute(query, (email, reset_token, datetime.now()))
            user = cursor.fetchone()
            
            if user:
                query = "UPDATE users SET password = %s, reset_token = NULL, reset_token_expiry = NULL WHERE email = %s"
                cursor.execute(query, (new_password, email))
                get_db().commit()
                flash("Password reset successfully", "success")
                return redirect(url_for('login'))
            else:
                flash("Invalid reset token or email", "error")
        
        return render_template('reset_password.html')
    except Exception as e:
        print("Error in reset_password route:", e)
        flash("An error occurred during password reset. Please try again later.", "error")
    finally:
        if cursor:
            cursor.close()  # Close cursor if it's not None


@app.route('/send_email/<recipient_email>/<reset_token>')
def send_email(recipient_email, reset_token):
    try:
        # Render HTML content using a Jinja2 template
        html_body = render_template('email_template.html', reset_token=reset_token)

        # Create a Message object
        msg = Message('Password Reset', sender='cineseek123@gmail.com', recipients=[recipient_email])
        msg.body = f'Your reset token is: {reset_token}'  # Plain text body
        msg.html = html_body  # HTML content

        # Send the email using Flask-Mail
        mail.send(msg)

        print("Email sent successfully")
        return 'Email sent successfully'
    except Exception as e:
        print(f"Failed to send email: {e}")
        return 'Failed to send email'


    

# Logout route
@app.route('/logout')
def logout():
    try:
        # Remove user-related session data
        session.pop('user_id', None)
        session.pop('username', None)
        session.pop('email', None)

        # Close the database connection
        db = get_db()
        if db:
            db.close()

        # Redirect the user to the login page
        return redirect(url_for('login'))
    except Exception as e:
        print("Error in logout route:", e)
        flash("An error occurred during logout. Please try again later.", "error")

# Add route for adding or removing movies from watchlist
@app.route('/add_to_watchlist', methods=['POST'])
def add_to_watchlist():
    if 'user_id' in session:
        user_id = session['user_id']
        if request.method == 'POST':
            movie_id = request.form['movie_id']
            title = request.form['title']
            date_added = datetime.now()

            try:
                cursor = get_cursor()

                # Check if the movie is already in the watchlist
                query = "SELECT * FROM watchlist WHERE user_id = %s AND movie_id = %s"
                cursor.execute(query, (user_id, movie_id))
                existing_movie = cursor.fetchone()

                if existing_movie:
                    # If movie already exists in watchlist, remove it
                    remove_query = "DELETE FROM watchlist WHERE user_id = %s AND movie_id = %s"
                    cursor.execute(remove_query, (user_id, movie_id))
                    get_db().commit()
                    flash("Movie removed from watchlist", "success")
                else:
                    # If movie doesn't exist in watchlist, add it
                    add_query = "INSERT INTO watchlist (user_id, movie_id, title, date_added) VALUES (%s, %s, %s, %s)"
                    cursor.execute(add_query, (user_id, movie_id, title, date_added))
                    get_db().commit()
                    flash("Movie added to watchlist", "success")

                return redirect(url_for('main_page'))
            except Exception as e:
                print("Error:", e)
                get_db().rollback()
                flash("An error occurred. Please try again.", "error")
            finally:
                cursor.close()
    else:
        flash("Please login to add movies to watchlist", "error")
        return redirect(url_for('login'))

def establish_connection():
    try:
        # Connect to the database
        cnx = mysql.connector.connect(user='Monesha', password='SriRam33Lak$', host='Monesha', database='movie_review_sys')
        print("Connected to the database successfully!")
        return cnx
    except mysql.connector.Error as err:
        print("Error connecting to the database:", err)
        return None

# Define a retry decorator with parameters to control the retry behavior
@retry(wait_fixed=2000, stop_max_attempt_number=3)  # Retry every 2 seconds, up to 3 attempts
def execute_query(query):
    try:
        # Connect to MySQL database
        connection = establish_connection()
        if connection:
            cursor = connection.cursor()

            # Execute the query
            cursor.execute(query)

            # Commit changes to the database
            connection.commit()

            # Close cursor and connection
            cursor.close()
            connection.close()

    except mysql.connector.Error as err:
        # Log the error or handle it as needed
        print("MySQL Error:", err)
        # Raise the error to trigger retry

# Example usage:
query = "SELECT * FROM users;"
try:
    execute_query(query)
    print("Query executed successfully!")
except Exception as e:
    print("Failed to execute query:", e)

def login(username_email, password):
    try:
        # Establish a new database connection
        cnx = establish_connection()
        if cnx:
            # Create a cursor object
            cursor = cnx.cursor()

            # Query to check if the username/email and password match
            query = "SELECT * FROM users WHERE (username = %s OR email = %s) AND password = %s"

            # Execute the query with the provided username/email and password
            if cursor and cursor.is_connected():
                cursor.execute(query, (username_email, username_email, password))

                # Fetch the user details
                user = cursor.fetchone()

                # Check if user details are found
                if user:
                    return user
                else:
                    return None  # Return None if user details are not found

    except Exception as e:
        print("Error during login:", e)
        return None  # Return None in case of any error

    finally:
        # Close the cursor and connection
        if cursor:
            cursor.close()
        if cnx:
            cnx.close()

if __name__ == '__main__':
    app.run(debug=True)


