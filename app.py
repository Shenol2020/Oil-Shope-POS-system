from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta
import json
from functools import wraps
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'

# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '1234',  # Change this
    'database': 'oil_shop_db'
}

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM employees WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        if user_data:
            return User(user_data['id'], user_data['username'], user_data['role'])
    return None

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Database connection error: {e}")
        return None

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                return jsonify({'error': 'Unauthorized access'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM employees WHERE username = %s", (username,))
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if user_data and check_password_hash(user_data['password'], password):
                user = User(user_data['id'], user_data['username'], user_data['role'])
                login_user(user)
                return jsonify({'success': True, 'role': user_data['role']})
            
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/sales')
@login_required
def sales_page():
    return render_template('sales.html', user=current_user)

@app.route('/inventory')
@login_required
def inventory_page():
    return render_template('inventory.html', user=current_user)

@app.route('/suppliers')
@login_required
@role_required('admin', 'manager')
def suppliers_page():
    return render_template('suppliers.html', user=current_user)

@app.route('/reports')
@login_required
def reports_page():
    return render_template('reports.html', user=current_user)

@app.route('/users')
@login_required
@role_required('admin')
def users_page():
    return render_template('users.html', user=current_user)

# API Endpoints

# Product APIs
@app.route('/api/products', methods=['GET'])
@login_required
def get_products():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.*, s.name as supplier_name 
            FROM products p 
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            ORDER BY p.name
        """)
        products = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(products)
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/products/<barcode>', methods=['GET'])
@login_required
def get_product_by_barcode(barcode):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT p.*, s.name as supplier_name 
            FROM products p 
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE p.barcode = %s
        """, (barcode,))
        product = cursor.fetchone()
        cursor.close()
        conn.close()
        if product:
            return jsonify(product)
        return jsonify({'error': 'Product not found'}), 404
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/products', methods=['POST'])
@login_required
@role_required('admin', 'manager')
def add_product():
    data = request.get_json()
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO products (name, barcode, category, price, cost_price, quantity, 
                                    min_stock_level, supplier_id, description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (data['name'], data['barcode'], data['category'], data['price'], 
                  data.get('cost_price', 0), data['quantity'], data.get('min_stock_level', 10),
                  data.get('supplier_id'), data.get('description', '')))
            conn.commit()
            product_id = cursor.lastrowid
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'id': product_id})
        except Error as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/products/<int:product_id>', methods=['PUT'])
@login_required
@role_required('admin', 'manager')
def update_product(product_id):
    data = request.get_json()
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE products 
                SET name=%s, barcode=%s, category=%s, price=%s, cost_price=%s, 
                    quantity=%s, min_stock_level=%s, supplier_id=%s, description=%s
                WHERE id=%s
            """, (data['name'], data['barcode'], data['category'], data['price'],
                  data.get('cost_price', 0), data['quantity'], data.get('min_stock_level', 10),
                  data.get('supplier_id'), data.get('description', ''), product_id))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'success': True})
        except Error as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_product(product_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM products WHERE id=%s", (product_id,))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'success': True})
        except Error as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Database connection failed'}), 500

# Sales APIs
@app.route('/api/sales', methods=['POST'])
@login_required
def create_sale():
    data = request.get_json()
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            # Create sale record
            cursor.execute("""
                INSERT INTO sales (customer_name, customer_phone, total_amount, 
                                 discount, payment_method, employee_id)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (data.get('customer_name', 'Walk-in'), data.get('customer_phone', ''),
                  data['total_amount'], data.get('discount', 0), 
                  data.get('payment_method', 'cash'), current_user.id))
            
            sale_id = cursor.lastrowid
            
            # Add sale items and update inventory
            for item in data['items']:
                cursor.execute("""
                    INSERT INTO sale_items (sale_id, product_id, quantity, price, subtotal)
                    VALUES (%s, %s, %s, %s, %s)
                """, (sale_id, item['product_id'], item['quantity'], 
                      item['price'], item['subtotal']))
                
                # Update product quantity
                cursor.execute("""
                    UPDATE products SET quantity = quantity - %s WHERE id = %s
                """, (item['quantity'], item['product_id']))
            
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'sale_id': sale_id})
        except Error as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/sales', methods=['GET'])
@login_required
def get_sales():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT s.*, e.username as employee_name,
                   COUNT(si.id) as items_count
            FROM sales s
            LEFT JOIN employees e ON s.employee_id = e.id
            LEFT JOIN sale_items si ON s.id = si.sale_id
        """
        params = []
        
        if start_date and end_date:
            query += " WHERE DATE(s.created_at) BETWEEN %s AND %s"
            params = [start_date, end_date]
        
        query += " GROUP BY s.id ORDER BY s.created_at DESC"
        
        cursor.execute(query, params)
        sales = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(sales)
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/sales/<int:sale_id>/items', methods=['GET'])
@login_required
def get_sale_items(sale_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT si.*, p.name as product_name
            FROM sale_items si
            JOIN products p ON si.product_id = p.id
            WHERE si.sale_id = %s
        """, (sale_id,))
        items = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(items)
    return jsonify({'error': 'Database connection failed'}), 500

# Supplier APIs
@app.route('/api/suppliers', methods=['GET'])
@login_required
def get_suppliers():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM suppliers ORDER BY name")
        suppliers = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(suppliers)
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/suppliers', methods=['POST'])
@login_required
@role_required('admin', 'manager')
def add_supplier():
    data = request.get_json()
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO suppliers (name, contact_person, phone, email, address)
                VALUES (%s, %s, %s, %s, %s)
            """, (data['name'], data.get('contact_person', ''), 
                  data.get('phone', ''), data.get('email', ''), data.get('address', '')))
            conn.commit()
            supplier_id = cursor.lastrowid
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'id': supplier_id})
        except Error as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
@login_required
@role_required('admin', 'manager')
def update_supplier(supplier_id):
    data = request.get_json()
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE suppliers 
                SET name=%s, contact_person=%s, phone=%s, email=%s, address=%s
                WHERE id=%s
            """, (data['name'], data.get('contact_person', ''), 
                  data.get('phone', ''), data.get('email', ''), 
                  data.get('address', ''), supplier_id))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'success': True})
        except Error as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_supplier(supplier_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM suppliers WHERE id=%s", (supplier_id,))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'success': True})
        except Error as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Database connection failed'}), 500

# Dashboard Stats API
@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        
        # Today's sales
        cursor.execute("""
            SELECT COALESCE(SUM(total_amount), 0) as today_sales
            FROM sales
            WHERE DATE(created_at) = CURDATE()
        """)
        today_sales = cursor.fetchone()['today_sales']
        
        # Low stock products
        cursor.execute("""
            SELECT COUNT(*) as low_stock_count
            FROM products
            WHERE quantity <= min_stock_level
        """)
        low_stock_count = cursor.fetchone()['low_stock_count']
        
        # Total products
        cursor.execute("SELECT COUNT(*) as total_products FROM products")
        total_products = cursor.fetchone()['total_products']
        
        # Monthly sales
        cursor.execute("""
            SELECT COALESCE(SUM(total_amount), 0) as monthly_sales
            FROM sales
            WHERE MONTH(created_at) = MONTH(CURDATE()) 
            AND YEAR(created_at) = YEAR(CURDATE())
        """)
        monthly_sales = cursor.fetchone()['monthly_sales']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'today_sales': float(today_sales),
            'low_stock_count': low_stock_count,
            'total_products': total_products,
            'monthly_sales': float(monthly_sales)
        })
    return jsonify({'error': 'Database connection failed'}), 500

# Low stock alerts
@app.route('/api/inventory/low-stock', methods=['GET'])
@login_required
def get_low_stock():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM products 
            WHERE quantity <= min_stock_level 
            ORDER BY quantity ASC
        """)
        products = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(products)
    return jsonify({'error': 'Database connection failed'}), 500

# User Management APIs
@app.route('/api/users', methods=['GET'])
@login_required
@role_required('admin')
def get_users():
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, username, role, created_at FROM employees ORDER BY username")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify(users)
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/users', methods=['POST'])
@login_required
@role_required('admin')
def add_user():
    data = request.get_json()
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            hashed_password = generate_password_hash(data['password'])
            cursor.execute("""
                INSERT INTO employees (username, password, role)
                VALUES (%s, %s, %s)
            """, (data['username'], hashed_password, data['role']))
            conn.commit()
            user_id = cursor.lastrowid
            cursor.close()
            conn.close()
            return jsonify({'success': True, 'id': user_id})
        except Error as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Database connection failed'}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot delete your own account'}), 400
    
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM employees WHERE id=%s", (user_id,))
            conn.commit()
            cursor.close()
            conn.close()
            return jsonify({'success': True})
        except Error as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({'error': str(e)}), 400
    return jsonify({'error': 'Database connection failed'}), 500

# Invoice Generation
@app.route('/api/sales/<int:sale_id>/invoice', methods=['GET'])
@login_required
def generate_invoice(sale_id):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        
        # Get sale details
        cursor.execute("""
            SELECT s.*, e.username as employee_name
            FROM sales s
            LEFT JOIN employees e ON s.employee_id = e.id
            WHERE s.id = %s
        """, (sale_id,))
        sale = cursor.fetchone()
        
        # Get sale items
        cursor.execute("""
            SELECT si.*, p.name as product_name
            FROM sale_items si
            JOIN products p ON si.product_id = p.id
            WHERE si.sale_id = %s
        """, (sale_id,))
        items = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Generate PDF
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Header
        p.setFont("Helvetica-Bold", 20)
        p.drawString(1*inch, height - 1*inch, "OIL SHOP INVOICE")
        
        # Invoice details
        p.setFont("Helvetica", 10)
        y = height - 1.5*inch
        p.drawString(1*inch, y, f"Invoice #: {sale_id}")
        p.drawString(1*inch, y - 0.2*inch, f"Date: {sale['created_at']}")
        p.drawString(1*inch, y - 0.4*inch, f"Customer: {sale['customer_name']}")
        p.drawString(1*inch, y - 0.6*inch, f"Phone: {sale['customer_phone']}")
        
        # Items table
        y = y - 1.2*inch
        p.setFont("Helvetica-Bold", 10)
        p.drawString(1*inch, y, "Product")
        p.drawString(4*inch, y, "Qty")
        p.drawString(5*inch, y, "Price")
        p.drawString(6*inch, y, "Subtotal")
        
        y -= 0.3*inch
        p.setFont("Helvetica", 10)
        
        for item in items:
            p.drawString(1*inch, y, item['product_name'][:30])
            p.drawString(4*inch, y, str(item['quantity']))
            p.drawString(5*inch, y, f"${item['price']:.2f}")
            p.drawString(6*inch, y, f"${item['subtotal']:.2f}")
            y -= 0.2*inch
        
        # Totals
        y -= 0.3*inch
        p.setFont("Helvetica-Bold", 10)
        p.drawString(5*inch, y, "Discount:")
        p.drawString(6*inch, y, f"${sale['discount']:.2f}")
        y -= 0.2*inch
        p.drawString(5*inch, y, "Total:")
        p.drawString(6*inch, y, f"${sale['total_amount']:.2f}")
        
        p.showPage()
        p.save()
        
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f'invoice_{sale_id}.pdf', mimetype='application/pdf')
    
    return jsonify({'error': 'Sale not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)