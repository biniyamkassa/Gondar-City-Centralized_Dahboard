from flask import Flask, render_template, request, jsonify, redirect, url_for, session, Response
import psycopg2
from psycopg2 import sql
import secrets
import hashlib
import json
import io
from datetime import datetime, date
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

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

# Register fonts


def register_fonts():
    """Register all required fonts"""
    fonts_registered = False

    # Try to register Amharic font first
    font_path = 'static/fonts/NotoSansEthiopic-Regular.ttf'
    try:
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont('Amharic', font_path))
            print("✅ Amharic font registered successfully!")
            fonts_registered = True
        else:
            print("❌ Amharic font not found at:", os.path.abspath(font_path))
            # List files in fonts directory for debugging
            fonts_dir = 'static/fonts'
            if os.path.exists(fonts_dir):
                print("📁 Files in fonts directory:", os.listdir(fonts_dir))
            else:
                print("❌ Fonts directory does not exist")
    except Exception as e:
        print(f"❌ Error registering Amharic font: {e}")

    # Always register default fonts as fallback
    try:
        # These are built-in ReportLab fonts that should always work
        pdfmetrics.registerFont(TTFont('Helvetica', 'Helvetica'))
        pdfmetrics.registerFont(TTFont('Helvetica-Bold', 'Helvetica-Bold'))
        print("✅ Default fonts registered")
    except:
        print("⚠️  Using built-in fonts")

    return fonts_registered


# Register fonts on startup
amharic_font_available = register_fonts()


def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        # Set encoding to support Amharic
        conn.set_client_encoding('UTF8')
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
                    # Handle Amharic text by ensuring proper encoding
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


def safe_string(value):
    """Convert value to string safely"""
    if value is None:
        return ""
    try:
        return str(value)
    except:
        return ""


def create_paragraph_with_font(text, font_size=12, alignment=0, bold=False):
    """Create paragraph with Amharic font support"""
    styles = getSampleStyleSheet()

    # Choose font family based on availability
    if amharic_font_available:
        font_name = 'Amharic'
        print(f"🔤 Using Amharic font for: {text[:50]}...")
    else:
        font_name = 'Helvetica-Bold' if bold else 'Helvetica'
        print(f"⚠️  Using fallback font for: {text[:50]}...")

    style = ParagraphStyle(
        'CustomStyle',
        parent=styles['Normal'],
        fontSize=font_size,
        alignment=alignment,
        fontName=font_name
    )
    return Paragraph(str(text), style)


def create_table_with_font_support(data):
    """Create a table with proper font support"""
    if not data or len(data) == 0:
        return None

    try:
        table = Table(data, repeatRows=1)

        # Choose font based on availability
        if amharic_font_available:
            font_name = 'Amharic'
            print("🔤 Creating table with Amharic font")
        else:
            font_name = 'Helvetica'
            print("⚠️  Creating table with fallback font")

        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        return table
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        return None


@app.route('/export_user_data_pdf')
def export_user_data_pdf():
    """Export all user data as PDF"""
    print("🔍 Starting PDF export for user data...")

    if 'username' not in session:
        print("❌ User not logged in")
        return jsonify({'success': False, 'message': 'Not logged in'})

    username = session['username']
    print(f"📊 Exporting data for user: {username}")
    print(f"🔤 Amharic font available: {amharic_font_available}")

    try:
        # Create PDF buffer
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = []

        # Add title with font support
        elements.append(create_paragraph_with_font(
            f"DATA REPORT - {username}", 16, 1, True))
        elements.append(create_paragraph_with_font(
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 10, 1))
        elements.append(Spacer(1, 20))

        conn = get_db_connection()
        if not conn:
            elements.append(create_paragraph_with_font(
                "Error: Could not connect to database", 12, 0))
            print("❌ Database connection failed")
        else:
            try:
                cur = conn.cursor()

                # Get tables user has permission to access
                cur.execute(
                    "SELECT table_name FROM user_table_permissions WHERE username = %s", (username,))
                user_tables = [row[0] for row in cur.fetchall()]
                print(f"📋 Found tables: {user_tables}")

                if not user_tables:
                    elements.append(create_paragraph_with_font(
                        "No tables assigned to user", 12, 0))
                    print("ℹ️  No tables found for user")

                for table_name in user_tables:
                    print(f"📄 Processing table: {table_name}")
                    elements.append(create_paragraph_with_font(
                        f"Table: {table_name}", 14, 0, True))

                    # Get data from table
                    try:
                        cur.execute(
                            f'SELECT * FROM "{table_name}" WHERE submitted_by = %s ORDER BY created_at DESC', (username,))
                        records = cur.fetchall()
                        print(
                            f"📊 Found {len(records)} records in table {table_name}")

                        if records:
                            # Get column names
                            cur.execute(f"""
                                SELECT column_name 
                                FROM information_schema.columns 
                                WHERE table_name = %s 
                                ORDER BY ordinal_position
                            """, (table_name,))
                            columns = [safe_string(row[0])
                                       for row in cur.fetchall()]
                            print(f"📝 Columns: {columns}")

                            # Prepare table data
                            table_data = [columns]  # Header row

                            for record in records:
                                row_data = []
                                for cell in record:
                                    if cell is None:
                                        row_data.append("")
                                    elif isinstance(cell, (datetime, date)):
                                        row_data.append(
                                            cell.strftime('%Y-%m-%d %H:%M:%S'))
                                    else:
                                        row_data.append(safe_string(cell))
                                table_data.append(row_data)

                            # Create and add table
                            table = create_table_with_font_support(table_data)
                            if table:
                                elements.append(table)
                                elements.append(Spacer(1, 15))

                            elements.append(create_paragraph_with_font(
                                f"Total records: {len(records)}", 10, 0))
                        else:
                            elements.append(create_paragraph_with_font(
                                "No data in this table", 10, 0))

                    except Exception as e:
                        error_msg = f"Error reading table {table_name}: {str(e)}"
                        print(f"❌ {error_msg}")
                        elements.append(
                            create_paragraph_with_font(error_msg, 10, 0))

                    elements.append(Spacer(1, 20))

                cur.close()
                conn.close()

            except Exception as e:
                error_msg = f"Database error: {str(e)}"
                print(f"❌ {error_msg}")
                elements.append(create_paragraph_with_font(error_msg, 10, 0))

        # Build PDF
        print("📄 Building PDF document...")
        doc.build(elements)
        buffer.seek(0)

        file_size = len(buffer.getvalue())
        print(f"✅ PDF generated successfully! File size: {file_size} bytes")

        return Response(
            buffer,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment;filename=Data_Report_{username}_{datetime.now().strftime('%Y%m%d')}.pdf"}
        )

    except Exception as e:
        print(f"❌ Critical error in PDF generation: {e}")
        # Return a simple error PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = []
        elements.append(create_paragraph_with_font(
            "ERROR GENERATING REPORT", 16, 1, True))
        elements.append(create_paragraph_with_font(f"Error: {str(e)}", 10, 0))
        doc.build(elements)
        buffer.seek(0)
        return Response(
            buffer,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment;filename=Error_Report_{datetime.now().strftime('%Y%m%d')}.pdf"}
        )


@app.route('/export_form_data_pdf')
def export_form_data_pdf():
    """Export specific form data as PDF"""
    print("🔍 Starting form-specific PDF export...")

    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    username = session['username']
    table_name = request.args.get('table_name', '')

    if not table_name:
        return jsonify({'success': False, 'message': 'Table name required'})

    print(f"📊 Exporting table {table_name} for user {username}")
    print(f"🔤 Amharic font available: {amharic_font_available}")

    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = []

        elements.append(create_paragraph_with_font(
            f"FORM DATA REPORT: {table_name}", 14, 1, True))
        elements.append(create_paragraph_with_font(f"User: {username}", 10, 1))
        elements.append(create_paragraph_with_font(
            f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 10, 1))
        elements.append(Spacer(1, 20))

        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()

                # Get data
                cur.execute(
                    f'SELECT * FROM "{table_name}" WHERE submitted_by = %s ORDER BY created_at DESC', (username,))
                records = cur.fetchall()
                print(f"📊 Found {len(records)} records in table {table_name}")

                if records:
                    # Get column names
                    cur.execute(f"""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = %s 
                        ORDER BY ordinal_position
                    """, (table_name,))
                    columns = [safe_string(row[0]) for row in cur.fetchall()]

                    # Prepare table data
                    table_data = [columns]
                    for record in records:
                        row_data = []
                        for cell in record:
                            if cell is None:
                                row_data.append("")
                            elif isinstance(cell, (datetime, date)):
                                row_data.append(
                                    cell.strftime('%Y-%m-%d %H:%M:%S'))
                            else:
                                row_data.append(safe_string(cell))
                        table_data.append(row_data)

                    # Create table
                    table = create_table_with_font_support(table_data)
                    if table:
                        elements.append(table)
                else:
                    elements.append(create_paragraph_with_font(
                        "No data available", 10, 0))

                cur.close()
                conn.close()

            except Exception as e:
                error_msg = f"Error reading table: {str(e)}"
                print(f"❌ {error_msg}")
                elements.append(create_paragraph_with_font(error_msg, 10, 0))
        else:
            elements.append(create_paragraph_with_font(
                "Database connection failed", 10, 0))

        doc.build(elements)
        buffer.seek(0)

        file_size = len(buffer.getvalue())
        print(
            f"✅ Form PDF generated successfully! File size: {file_size} bytes")

        return Response(
            buffer,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment;filename={table_name}_report_{datetime.now().strftime('%Y%m%d')}.pdf"}
        )

    except Exception as e:
        print(f"❌ Critical error in form PDF generation: {e}")
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = []
        elements.append(create_paragraph_with_font(
            "ERROR GENERATING FORM REPORT", 16, 1, True))
        elements.append(create_paragraph_with_font(f"Error: {str(e)}", 10, 0))
        doc.build(elements)
        buffer.seek(0)
        return Response(
            buffer,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment;filename=Error_Form_Report_{datetime.now().strftime('%Y%m%d')}.pdf"}
        )


@app.route('/export_summary_pdf')
def export_summary_pdf():
    """Export summary report"""
    print("🔍 Starting summary PDF export...")

    if 'username' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'})

    username = session['username']
    print(f"🔤 Amharic font available: {amharic_font_available}")

    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = []

        elements.append(create_paragraph_with_font(
            f"SUMMARY REPORT - {username}", 16, 1, True))
        elements.append(create_paragraph_with_font(
            f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 10, 1))
        elements.append(Spacer(1, 20))

        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()

                # Get user tables
                cur.execute(
                    "SELECT table_name FROM user_table_permissions WHERE username = %s", (username,))
                user_tables = [row[0] for row in cur.fetchall()]
                print(f"📋 Found tables for summary: {user_tables}")

                summary_data = [['Table Name', 'Record Count']]
                total_records = 0

                for table_name in user_tables:
                    # Get actual record count
                    cur.execute(
                        f'SELECT COUNT(*) FROM "{table_name}" WHERE submitted_by = %s', (username,))
                    actual_count = cur.fetchone()[0]
                    summary_data.append([table_name, str(actual_count)])
                    total_records += actual_count
                    print(f"📊 Table {table_name}: {actual_count} records")

                # Summary table
                if len(summary_data) > 1:
                    table = create_table_with_font_support(summary_data)
                    if table:
                        elements.append(table)
                        elements.append(Spacer(1, 20))
                    elements.append(create_paragraph_with_font(
                        f"Total Records: {total_records}", 14, 0))
                else:
                    elements.append(create_paragraph_with_font(
                        "No data available", 10, 0))

                cur.close()
                conn.close()

            except Exception as e:
                error_msg = f"Error generating summary: {str(e)}"
                print(f"❌ {error_msg}")
                elements.append(create_paragraph_with_font(error_msg, 10, 0))
        else:
            elements.append(create_paragraph_with_font(
                "Database connection failed", 10, 0))

        doc.build(elements)
        buffer.seek(0)

        file_size = len(buffer.getvalue())
        print(
            f"✅ Summary PDF generated successfully! File size: {file_size} bytes")

        return Response(
            buffer,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment;filename=Summary_Report_{username}_{datetime.now().strftime('%Y%m%d')}.pdf"}
        )

    except Exception as e:
        print(f"❌ Critical error in summary PDF generation: {e}")
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        elements = []
        elements.append(create_paragraph_with_font(
            "ERROR GENERATING SUMMARY", 16, 1, True))
        elements.append(create_paragraph_with_font(f"Error: {str(e)}", 10, 0))
        doc.build(elements)
        buffer.seek(0)
        return Response(
            buffer,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment;filename=Error_Summary_{datetime.now().strftime('%Y%m%d')}.pdf"}
        )


if __name__ == '__main__':
    app.run(debug=True, port=5000)
