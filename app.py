from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import psycopg2
from psycopg2 import sql
import secrets
import hashlib
import json

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'postgres',
    'password': 'Bini@283#',
    'database': 'bini_database'
}


def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def initialize_database():
    """Initialize the database with required tables"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Create system_users table if not exists
            cur.execute('''
                CREATE TABLE IF NOT EXISTS system_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password VARCHAR(100) NOT NULL,
                    email VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Create user_table_permissions table if not exists
            cur.execute('''
                CREATE TABLE IF NOT EXISTS user_table_permissions (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) NOT NULL,
                    table_name VARCHAR(100) NOT NULL,
                    can_read BOOLEAN DEFAULT TRUE,
                    can_write BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(username, table_name)
                )
            ''')

            # Create table_dropdown_options table if not exists
            cur.execute('''
                CREATE TABLE IF NOT EXISTS table_dropdown_options (
                    id SERIAL PRIMARY KEY,
                    table_name VARCHAR(100) NOT NULL,
                    column_name VARCHAR(100) NOT NULL,
                    option_value VARCHAR(255) NOT NULL,
                    option_label VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(table_name, column_name, option_value)
                )
            ''')

            conn.commit()
            cur.close()
            conn.close()
            print("Database initialization completed successfully")

        except Exception as e:
            print(f"Error initializing database: {e}")
            if conn:
                conn.rollback()
    else:
        print("Failed to connect to database for initialization")


# Initialize database when the app starts
print("Starting database initialization...")
initialize_database()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/admin')
def admin():
    return render_template('admin.html')


@app.route('/user_login')
def user_login():
    return render_template('user_login.html')


@app.route('/user_dashboard')
def user_dashboard():
    if 'user_id' not in session:
        return redirect('/user_login')
    return render_template('user_dashboard.html')


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    # Ensure database is initialized
    initialize_database()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, username, password FROM system_users WHERE username = %s",
                (username,)
            )
            user = cur.fetchone()
            cur.close()
            conn.close()

            if user and user[2] == hash_password(password):
                session['user_id'] = user[0]
                session['username'] = user[1]
                return jsonify({'success': True, 'message': 'Login successful!'})
            else:
                return jsonify({'success': False, 'message': 'Invalid username or password'})

        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'Database connection failed'})


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/create_user', methods=['POST'])
def create_user():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')

    # Ensure database is initialized before creating user
    initialize_database()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Insert the user with hashed password
            hashed_password = hash_password(password)
            cur.execute(
                "INSERT INTO system_users (username, password, email) VALUES (%s, %s, %s)",
                (username, hashed_password, email)
            )

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({'success': True, 'message': f'User {username} created successfully!'})

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'Database connection failed'})


@app.route('/create_table', methods=['POST'])
def create_table():
    data = request.json
    table_name = data.get('tableName')
    columns = data.get('columns', [])
    assigned_user = data.get('assignedUser', '')
    dropdown_options = data.get('dropdownOptions', {})

    # Ensure database is initialized
    initialize_database()

    conn = get_db_connection()

    if conn:
        try:
            cur = conn.cursor()

            # Build column definitions
            column_definitions = []
            for col in columns:
                col_name = col['name']
                col_type = col['type']
                column_definitions.append(f'"{col_name}" {col_type}')

            # Create main table
            create_table_query = f'''
                CREATE TABLE IF NOT EXISTS "{table_name}" (
                    id SERIAL PRIMARY KEY,
                    {', '.join(column_definitions)},
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    submitted_by VARCHAR(100)
                )
            '''

            cur.execute(create_table_query)

            # Save dropdown options if any
            for column_name, options in dropdown_options.items():
                for option in options:
                    if option['value'] and option['label']:
                        cur.execute('''
                            INSERT INTO table_dropdown_options 
                            (table_name, column_name, option_value, option_label)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (table_name, column_name, option_value) 
                            DO UPDATE SET option_label = EXCLUDED.option_label
                        ''', (table_name, column_name, option['value'], option['label']))

            # If a user is assigned to this table, create permission
            if assigned_user:
                cur.execute('''
                    INSERT INTO user_table_permissions (username, table_name, can_read, can_write)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (username, table_name) 
                    DO UPDATE SET can_write = EXCLUDED.can_write
                ''', (assigned_user, table_name, True, True))

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({'success': True, 'message': f'Table {table_name} created successfully in bini_database!'})

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'Database connection failed'})


@app.route('/get_users')
def get_users():
    """Get all users for assignment dropdown"""
    # Ensure database is initialized
    initialize_database()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT username FROM system_users ORDER BY username")
            users = [row[0] for row in cur.fetchall()]
            cur.close()
            conn.close()
            return jsonify({'success': True, 'users': users})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'Database connection failed'})


@app.route('/get_tables')
def get_tables():
    """Get all tables (for admin)"""
    # Ensure database is initialized
    initialize_database()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                AND table_name NOT IN ('system_users', 'user_table_permissions', 'table_dropdown_options')
                ORDER BY table_name
            """)
            tables = [row[0] for row in cur.fetchall()]
            cur.close()
            conn.close()
            return jsonify({'success': True, 'tables': tables})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'Database connection failed'})


@app.route('/get_user_tables')
def get_user_tables():
    """Get tables assigned to the logged-in user"""
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    # Ensure database is initialized
    initialize_database()

    username = session['username']
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT table_name FROM user_table_permissions 
                WHERE username = %s AND can_write = TRUE
                ORDER BY table_name
            """, (username,))

            tables = [row[0] for row in cur.fetchall()]
            cur.close()
            conn.close()
            return jsonify({'success': True, 'tables': tables})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'Database connection failed'})


@app.route('/get_table_columns/<table_name>')
def get_table_columns(table_name):
    """Get columns for a specific table"""
    # Ensure database is initialized
    initialize_database()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = %s 
                    AND column_name NOT IN ('id', 'created_at', 'submitted_by')
                ORDER BY ordinal_position
            """, (table_name,))

            columns = [{'name': row[0], 'type': row[1]}
                       for row in cur.fetchall()]

            # Get dropdown options for each column
            dropdown_options = {}
            for column in columns:
                cur.execute("""
                    SELECT option_value, option_label 
                    FROM table_dropdown_options 
                    WHERE table_name = %s AND column_name = %s
                    ORDER BY option_value
                """, (table_name, column['name']))

                options = cur.fetchall()
                if options:
                    dropdown_options[column['name']] = [
                        {'value': row[0], 'label': row[1]} for row in options
                    ]

            cur.close()
            conn.close()
            return jsonify({
                'success': True,
                'columns': columns,
                'dropdownOptions': dropdown_options
            })
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'Database connection failed'})


@app.route('/submit_form_data', methods=['POST'])
def submit_form_data():
    data = request.json
    table_name = data.get('tableName')
    form_data = data.get('formData', {})

    # Check if user has permission to write to this table
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    # Ensure database is initialized
    initialize_database()

    username = session['username']
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Check user permissions
            cur.execute("""
                SELECT can_write FROM user_table_permissions 
                WHERE username = %s AND table_name = %s
            """, (username, table_name))

            permission = cur.fetchone()
            if not permission or not permission[0]:
                return jsonify({'success': False, 'message': 'You do not have permission to submit data to this table'})

            # Get column information (excluding system columns)
            cur.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name NOT IN ('id', 'created_at', 'submitted_by')
            """, (table_name,))

            columns = cur.fetchall()

            # Prepare insert query
            column_names = [col[0] for col in columns]
            column_names.append('submitted_by')
            placeholders = ['%s'] * len(column_names)
            values = []

            # Convert values based on data type
            for col_name, data_type in columns:
                value = form_data.get(col_name, '')
                if 'int' in data_type and value:
                    try:
                        values.append(int(value))
                    except:
                        values.append(0)
                elif 'bool' in data_type:
                    values.append(bool(value))
                else:
                    values.append(str(value))

            # Add submitted_by value
            values.append(username)

            insert_query = f'''
                INSERT INTO "{table_name}" ({', '.join([f'"{col}"' for col in column_names])})
                VALUES ({', '.join(placeholders)})
            '''

            cur.execute(insert_query, values)
            conn.commit()
            cur.close()
            conn.close()

            return jsonify({'success': True, 'message': 'Form data submitted successfully!'})

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'Database connection failed'})


@app.route('/get_user_submissions')
def get_user_submissions():
    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    # Ensure database is initialized
    initialize_database()

    username = session['username']
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            # Get tables user has permission to access
            cur.execute("""
                SELECT table_name FROM user_table_permissions 
                WHERE username = %s
            """, (username,))
            user_tables = [row[0] for row in cur.fetchall()]

            submissions = []
            for table in user_tables:
                cur.execute(f'''
                    SELECT id, created_at FROM "{table}" 
                    WHERE submitted_by = %s ORDER BY created_at DESC
                ''', (username,))

                user_records = cur.fetchall()
                for record in user_records:
                    submissions.append({
                        'table': table,
                        'record_id': record[0],
                        'submitted_at': record[1].strftime('%Y-%m-%d %H:%M:%S')
                    })

            cur.close()
            conn.close()
            return jsonify({'success': True, 'submissions': submissions})

        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'Database connection failed'})


@app.route('/assign_table_to_user', methods=['POST'])
def assign_table_to_user():
    """Assign a table to a user"""
    data = request.json
    username = data.get('username')
    table_name = data.get('tableName')

    # Ensure database is initialized
    initialize_database()

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()

            cur.execute('''
                INSERT INTO user_table_permissions (username, table_name, can_read, can_write)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (username, table_name) 
                DO UPDATE SET can_write = EXCLUDED.can_write
            ''', (username, table_name, True, True))

            conn.commit()
            cur.close()
            conn.close()

            return jsonify({'success': True, 'message': f'Table {table_name} assigned to user {username} successfully!'})

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': str(e)})

    return jsonify({'success': False, 'message': 'Database connection failed'})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
