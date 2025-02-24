import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Product, Order, OrderItem, CartItem
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ecommerce.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads/products'
app.config['RAZORPAY_KEY_ID'] = 'rzp_test_your_key_id'
app.config['RAZORPAY_KEY_SECRET'] = 'your_key_secret'

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# After db.init_app(app)
migrate = Migrate(app, db)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Add this function after db.init_app(app) and before the routes
def create_admin_user():
    with app.app_context():
        # Check if admin user already exists
        admin = User.query.filter_by(email='admin@example.com').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@example.com',
                password=generate_password_hash('admin123'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print('Admin user created successfully!')
            print('Email: admin@example.com')
            print('Password: admin123')

# Add this function after create_admin_user() and before the routes
def create_upload_directories():
    # Create directory for product images
    upload_dir = os.path.join(app.static_folder, 'uploads', 'products')
    os.makedirs(upload_dir, exist_ok=True)

# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            login_user(user)
            return redirect(url_for('admin_dashboard' if user.is_admin else 'products'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed_password = generate_password_hash(request.form.get('password'))
        user = User(
            username=request.form.get('username'),
            email=request.form.get('email'),
            password=hashed_password
        )
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Admin routes
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return redirect(url_for('products'))
    products = Product.query.all()
    return render_template('admin/dashboard.html', products=products)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@login_required
def add_product():
    if not current_user.is_admin:
        return redirect(url_for('products'))
    
    if request.method == 'POST':
        file = request.files['image']
        if file:
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_path = f'uploads/products/{filename}'
        else:
            image_path = None

        product = Product(
            name=request.form.get('name'),
            description=request.form.get('description'),
            price=float(request.form.get('price')),
            stock=int(request.form.get('stock')),
            image_path=image_path
        )
        db.session.add(product)
        db.session.commit()
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/add_product.html')

@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    if not current_user.is_admin:
        return redirect(url_for('products'))
    
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.description = request.form.get('description')
        product.price = float(request.form.get('price'))
        product.stock = int(request.form.get('stock'))
        
        file = request.files['image']
        if file and file.filename:
            # Delete old image if exists
            if product.image_path:
                old_image_path = os.path.join(app.static_folder, product.image_path)
                if os.path.exists(old_image_path):
                    os.remove(old_image_path)
            
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            product.image_path = f'uploads/products/{filename}'
        
        db.session.commit()
        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/edit_product.html', product=product)

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        return redirect(url_for('products'))
    users = User.query.filter(User.id != current_user.id).all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return redirect(url_for('products'))
    
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Cannot delete admin users', 'error')
        return redirect(url_for('admin_users'))
    
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user/<int:user_id>/orders')
@login_required
def user_orders(user_id):
    if not current_user.is_admin:
        return redirect(url_for('products'))
    
    user = User.query.get_or_404(user_id)
    orders = Order.query.filter_by(user_id=user_id).all()
    return render_template('admin/user_orders.html', user=user, orders=orders)

# User routes
@app.route('/')
@app.route('/products')
def products():
    products = Product.query.all()
    return render_template('user/products.html', products=products)

@app.route('/add-to-cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    quantity = int(request.form.get('quantity', 1))
    
    if quantity > product.stock:
        flash('Not enough stock available', 'error')
        return redirect(url_for('products'))
    
    # Check if item already in cart
    cart_item = CartItem.query.filter_by(
        user_id=current_user.id,
        product_id=product_id
    ).first()
    
    if cart_item:
        cart_item.quantity += quantity
    else:
        cart_item = CartItem(
            user_id=current_user.id,
            product_id=product_id,
            quantity=quantity
        )
        db.session.add(cart_item)
    
    db.session.commit()
    flash('Item added to cart!', 'success')
    return redirect(url_for('products'))

@app.route('/cart')
@login_required
def cart():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    total = sum(item.product.price * item.quantity for item in cart_items)
    return render_template('user/cart.html', cart_items=cart_items, total=total)

@app.route('/orders')
@login_required
def orders():
    user_orders = Order.query.filter_by(user_id=current_user.id).all()
    return render_template('user/orders.html', orders=user_orders)

@app.route('/remove-from-cart/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    cart_item = CartItem.query.get_or_404(item_id)
    if cart_item.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('cart'))
    
    db.session.delete(cart_item)
    db.session.commit()
    flash('Item removed from cart', 'success')
    return redirect(url_for('cart'))

# Add this mock function at the top of the file after imports
def create_mock_razorpay_order():
    """Create a mock Razorpay order response"""
    import uuid
    mock_order_id = f"order_{uuid.uuid4().hex}"
    return {
        'id': mock_order_id,
        'entity': 'order',
        'amount': 0,  # Will be set in the checkout route
        'currency': 'INR',
        'status': 'created',
        'receipt': None
    }

# Update the checkout route
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('Your cart is empty', 'error')
        return redirect(url_for('cart'))
    
    total = sum(item.product.price * item.quantity for item in cart_items)
    
    if request.method == 'POST':
        try:
            # Create mock Razorpay order instead of actual API call
            mock_order = create_mock_razorpay_order()
            mock_order['amount'] = int(total * 100)  # Set the actual amount
            
            # Create order in database
            order = Order(
                user_id=current_user.id,
                total_amount=total,
                status='pending',
                payment_id=mock_order['id']
            )
            db.session.add(order)
            db.session.flush()
            
            # Add order items
            for cart_item in cart_items:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=cart_item.product_id,
                    quantity=cart_item.quantity,
                    price=cart_item.product.price
                )
                db.session.add(order_item)
            
            db.session.commit()
            
            return render_template(
                'user/payment.html',
                order=order,
                razorpay_order_id=mock_order['id'],
                razorpay_key_id='rzp_test_mock_key_id'  # Use mock key
            )
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating your order. Please try again.', 'error')
            return redirect(url_for('cart'))
    
    return render_template('user/checkout.html', cart_items=cart_items, total=total)

# Update the verify_payment route
@app.route('/payment/verify', methods=['POST'])
@login_required
def verify_payment():
    try:
        # Create mock payment verification data
        import uuid
        mock_payment_id = f"pay_{uuid.uuid4().hex}"
        mock_signature = f"sig_{uuid.uuid4().hex}"
        
        # Get the order_id from the form
        order_id = request.form.get('razorpay_order_id')
        
        # Create mock response
        mock_response = {
            'razorpay_payment_id': mock_payment_id,
            'razorpay_order_id': order_id,
            'razorpay_signature': mock_signature
        }
        
        # Update order
        order = Order.query.filter_by(payment_id=order_id).first()
        if order:
            order.payment_status = 'completed'
            order.status = 'processing'
            order.payment_response = mock_response
            
            # Update product stock and clear cart
            cart_items = CartItem.query.filter_by(user_id=current_user.id).all()
            for cart_item in cart_items:
                product = cart_item.product
                product.stock -= cart_item.quantity
                db.session.delete(cart_item)
            
            db.session.commit()
            flash('Payment successful! Your order has been placed.', 'success')
            return redirect(url_for('order_success', order_id=order.id))
            
    except Exception as e:
        flash('Payment verification failed. Please contact support.', 'error')
    
    return redirect(url_for('orders'))

@app.route('/order/success/<int:order_id>')
@login_required
def order_success(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and not current_user.is_admin:
        return redirect(url_for('orders'))
    return render_template('user/order_success.html', order=order)

# Add this new route to update cart item quantity
@app.route('/update-cart/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    cart_item = CartItem.query.get_or_404(item_id)
    if cart_item.user_id != current_user.id:
        flash('Access denied', 'error')
        return redirect(url_for('cart'))
    
    new_quantity = int(request.form.get('quantity', 1))
    if new_quantity < 1:
        flash('Quantity must be at least 1', 'error')
        return redirect(url_for('cart'))
    
    # Check if enough stock is available
    if new_quantity > cart_item.product.stock:
        flash('Not enough stock available', 'error')
        return redirect(url_for('cart'))
    
    cart_item.quantity = new_quantity
    db.session.commit()
    flash('Cart updated successfully', 'success')
    return redirect(url_for('cart'))

# Modify the main block at the bottom of the file
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_admin_user()
        create_upload_directories()
    app.run(debug=True) 