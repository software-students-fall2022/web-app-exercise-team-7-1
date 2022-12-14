#!/usr/bin/env python3

from calendar import c
from crypt import methods
from flask import Flask, render_template, request, redirect, url_for, make_response, flash
from dotenv import dotenv_values
import random
import pymongo
import datetime
from bson.objectid import ObjectId


# modules useful for user authentication
import flask_login
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash

# instantiate the app
app = Flask(__name__)
app.secret_key = 'secret'  # Change this!

# set up flask-login for user authentication
login_manager = flask_login.LoginManager()
login_manager.init_app(app)

# load credentials and configuration options from .env file
# if you do not yet have a file named .env, make one based on the template in env.example
config = dotenv_values(".env")

# turn on debugging if in development mode
if config['FLASK_ENV'] == 'development':
    # turn on debugging, if in development
    app.debug = True # debug mnode

# connect to the database
cxn = pymongo.MongoClient(config['MONGO_URI'], serverSelectionTimeoutMS=5000)
try:
    # verify the connection works by pinging the database
    cxn.admin.command('ping') # The ping command is cheap and does not require auth.
    db = cxn[config['MONGO_DBNAME']] # store a reference to the database
    print(' *', 'Connected to MongoDB!') # if we get here, the connection worked!
except Exception as e:
    # the ping command failed, so the connection is not available.
    print(' *', "Failed to connect to MongoDB at", config['MONGO_URI'])
    print(' * ', 'Database connection error:', e) # debug


# a class to represent a user
class User(flask_login.UserMixin):
    # inheriting from the UserMixin class gives this blank class default implementations of the necessary methods that flask-login requires all User objects to have
    # see some discussion of this here: https://stackoverflow.com/questions/63231163/what-is-the-usermixin-in-flask
    def __init__(self, data):
        '''
        Constructor for User objects
        @param data: a dictionary containing the user's data pulled from the database
        '''
        self.id = data['_id'] # shortcut to the _id field
        self.data = data # all user data from the database is stored within the data field

def locate_user(user_id=None, email=None):
    '''
    Return a User object for the user with the given id or email address, or None if no such user exists.
    @param user_id: the user_id of the user to locate
    @param email: the email address of the user to locate
    '''
    if user_id:
        # loop up by user_id
        criteria = {"_id": ObjectId(user_id)}
    else:
        # loop up by email
        criteria = {"email": email}
    doc = db.users.find_one(criteria) # find a user with this email

    # if user exists in the database, create a User object and return it
    if doc:
        # return a user object representing this user
        user = User(doc)
        return user
    # else
    return None

@login_manager.user_loader
def user_loader(user_id):
    ''' 
    This function is called automatically by flask-login with every request the browser makes to the server.
    If there is an existing session, meaning the user has already logged in, then this function will return the logged-in user's data as a User object.
    @param user_id: the user_id of the user to load
    @return a User object if the user is logged-in, otherwise None
    '''
    return locate_user(user_id=user_id) # return a User object if a user with this user_id exists


# set up any context processors
# context processors allow us to make selected variables or functions available from within all templates

@app.context_processor
def inject_user():
    # make the currently-logged-in user, if any, available to all templates as 'user'
    return dict(user=flask_login.current_user)


# set up the routes

# route for the home page
@app.route('/')
def home():
    """
    Route for the home page
    """
    return render_template('login.html') 

@app.route('/all_cards')
def all_cards():
    cards = db.cards.find({})
    return render_template('all_cards.html', cards = cards) 

@app.route('/open_pack')
def open_pack():
    return render_template('open_pack.html')

#this route will handle the POST request from open_pack.html
@app.route('/card', methods=['POST'])
def card(): 
    rarity = ["basic","epic","legendary"]
    chances = [.80,.15,.05]
    lst = random.choices(rarity,chances, k=1)#returns a list
    rarity_picked = lst[0]
    cards = []
    for card in db.cards.find({"rarity":rarity_picked}):
        cards.append(card)
    card = random.choice(list(cards))
    db.users.update_one(
        {"_id": ObjectId(flask_login.current_user.id)},
        {
            "$push":{
                "cards":card
            }
        }
    )
    return render_template('card.html',card=card)

@app.route('/showcase')
def showcase():
    show = flask_login.current_user.data["showcase"]
    return render_template('showcase.html', show = show) 

@app.route('/user_showcase/<email>')
def showcase_email(email):
    show = db.users.find_one({
        "email":email
    },
    {
        "_id": 0,
        "showcase": 1
    })["showcase"]
    return render_template('user_showcase.html', show = show) 

@app.route('/selectShow', methods=['POST'])
def selectShow():

    card = eval(request.args.get('card'))
    index = request.args.get('index')
    db.users.update_one(
        {"_id": ObjectId(flask_login.current_user.id)},
        {
            "$set":{
                "showcase."+index:card
            }
        }
    )
    return redirect(url_for('showcase')) 

@app.route('/library/<index>')
def library(index):
    cards = flask_login.current_user.data["cards"]
    return render_template('library.html', cards = cards, index = index)

@app.route('/users_showcase')
def users_showcase():
    name = request.args.get('fname')
    results = db.users.find(
        {
            "email": {'$regex': f".*{name}.*", '$options': 'i'}
        }
    )
    return render_template('users_showcase.html', results = results)

@app.route('/leaderboard')
def leaderboard():
    cards = [
        {"$addFields":{"totalcards":{"$size": "$cards"}}},
        {"$sort": {"totalcards": -1}},
        {"$limit": 5}
    ]
    top5 = db.users.aggregate(cards)
    return render_template('leaderboard.html', top5 = top5) 

@app.route('/my_cards')
def my_cards():
    cards = flask_login.current_user.data["cards"]
    return render_template('my_cards.html', cards = cards)   

@app.route('/remove/<index>', methods=['GET', 'POST'])
def remove(index):
    db.users.update_one(
        {"_id": ObjectId(flask_login.current_user.id)},
        {
            "$set":{
                "showcase."+index:None
            }
        }
    )
    return redirect(url_for('showcase')) 

@app.route('/exchange',methods = ["GET","POST"])
def exchange():
    current_user = flask_login.current_user
    if request.method == "POST":
        if request.form["email"] != current_user.data["email"]:
            email = request.form['email']
            if locate_user(email=email) == None:
                error = "User not found, enter valid email"
                return render_template('exchange.html', error=error) 
            return render_template('exchange.html', email=email) 
        else:
            error = "Cant Choose Yourself Silly!"
            return render_template('exchange.html', error=error) 
    else:
        return render_template('exchange.html') 

@app.route('/gift/<email>')
def gift(email):
    cards = flask_login.current_user.data["cards"]
    return render_template("gift.html",email = email, cards = cards)

@app.route('/gift/<cardid>/<email>',methods=["POST"])
def gift_post(cardid,email):
    cards = flask_login.current_user.data["cards"]
    found = False
    for i in range(len(cards)):
        card = cards[i]
        if ObjectId(card["_id"]) == ObjectId(cardid):
            cards[-1],cards[i] = cards[i],cards[-1]
            cards.pop()
            break
    db.users.update_one(
        {"_id" : ObjectId(flask_login.current_user.id)},
        {
            "$set" : {
                "cards" : cards
            }
        }  
    )
    reciever = locate_user(email=email)
    db.users.update_one(
        {"_id": ObjectId(reciever.id)},
        {
            "$push": {
                "cards":card
            }
        }
    )
    return render_template("gift_confirmation.html", cardid = cardid, email=email)

@app.route('/trade/<email>')
def trade(email):
    cards = flask_login.current_user.data["cards"]
    return render_template("trade.html",cards = cards, email = email)

@app.route('/trade_select/<mycardid>/<email>', methods = ["POST"])
def trade_select(mycardid,email):
    mycard = db.cards.find_one({"_id" : ObjectId(mycardid)})
    other_user = locate_user(email=email)
    cards = other_user.data["cards"] 
    return render_template("trade_select.html", email = email, cards = cards, mycard=mycard)


@app.route('/trade_finsh/<cardid>/<email>/<mycardid>', methods = ["POST"])
def trade_finish(cardid,email,mycardid):
    makerid =flask_login.current_user.id
    other = locate_user(email=email)
    otherid= other.id
    maker_card = db.cards.find_one({"_id": ObjectId(mycardid)})
    reciever_card = db.cards.find_one({"_id": ObjectId(cardid)})
    db.requests.insert_one({"maker":ObjectId(makerid), "maker_card":maker_card,"reciever":ObjectId(otherid), "reciever_card":reciever_card})
    return render_template("trade_finish.html",cardid=cardid,email=email,mycardid=mycardid)
    

@app.route('/my_requests')
def my_requests():
    requests = db.requests.find({"reciever": ObjectId(flask_login.current_user.id)})
    return render_template("my_requests.html",requests=requests)

@app.route('/deny_request/<requestid>', methods =["POST"])
def deny_request(requestid):
    requests = db.requests.delete_one({"_id": ObjectId(requestid)})
    return redirect(url_for("my_requests"))

@app.route('/accept_request/<requestid>',methods =["POST"])
def accept_request(requestid):
    request = db.requests.find_one({"_id":ObjectId(requestid)})
    makerid = request["maker"]
    recieverid= request["reciever"]
    maker_card = request["maker_card"]
    reciever_card = request["reciever_card"]
    maker = db.users.find_one({"_id": makerid})
    reciever = db.users.find_one({"_id": recieverid})
    maker_cards = maker["cards"]
    reciever_cards = reciever["cards"]
    for i in range(len(maker_cards)):
        card = maker_cards[i]
        if card == maker_card:
            maker_cards[-1],maker_cards[i] = maker_cards[i],maker_cards[-1]
            maker_cards.pop()
            break
    maker_cards.append(reciever_card)
    db.users.update_one(
        {"_id" : ObjectId(makerid)},
        {
            "$set" : {
                "cards" : maker_cards
            }
        }  
    )
    for i in range(len(reciever_cards)):
        card = reciever_cards[i]
        if card == reciever_card:
            reciever_cards[-1],reciever_cards[i] = reciever_cards[i],reciever_cards[-1]
            reciever_cards.pop()
            break
    reciever_cards.append(maker_card)
    db.users.update_one(
        {"_id" : ObjectId(recieverid)},
        {
            "$set" : {
                "cards" : reciever_cards
            }
        }  
    )
    requests = db.requests.delete_one({"_id": ObjectId(requestid)})
    return redirect(url_for("my_requests"))

# route to show a signup form to the user
@app.route('/signup', methods=['GET'])
def signup():
    # if the current user is already signed in, there is no need to sign up, so redirect them
    if flask_login.current_user.is_authenticated:
        flash('You are already logged in, silly!') # flash can be used to pass a special message to the template we are about to render
        return redirect(url_for('home')) # tell the web browser to make a request for the / route (the home function)

    # else
    return render_template('signup.html') # render the login form template

# route to handle the submission of the login form
@app.route('/signup', methods=['POST'])
def signup_submit():
    # grab the data from the form submission
    email = request.form['email']
    password = request.form['password']
    hashed_password = generate_password_hash(password) # generate a hashed password to store - don't store the original
    
    # check whether an account with this email already exists... don't allow duplicates
    if locate_user(email=email):
        flash('An account for {} already exists.  Please log in.'.format(email))
        return redirect(url_for('login')) # redirect to login page

    # create a new document in the database for this new user
    user_id = db.users.insert_one({"email": email, "password": hashed_password, "cards": [], "showcase": [None] * 5}).inserted_id # hash the password and save it to the database
    if user_id:
        # successfully created a new user... make a nice user object
        user = User({
            "_id": user_id,
            "email": email,
            "password": hashed_password,
            "cards" : [],
            "showcase" : [None] * 5,
        })
        flask_login.login_user(user) # log in the user using flask-login
        flash('Thanks for joining, {}!'.format(user.data['email'])) # flash can be used to pass a special message to the template we are about to render
        return redirect(url_for('open_pack'))
    # else
    return 'Signup failed'

# route to show a login form to the user
@app.route('/login', methods=['GET'])
def login():
    # if the current user is already signed in, there is no need to sign up, so redirect them
    if flask_login.current_user.is_authenticated:
        flash('You are already logged in, silly!') # flash can be used to pass a special message to the template we are about to render
        return redirect(url_for('open_pack')) # tell the web browser to make a request for the / route (the home function)
    
    # else
    return render_template('login.html') # render the login form template

# route to handle the submission of the login form
@app.route('/login', methods=['POST'])
def login_submit():
    email = request.form['email']
    password = request.form['password']
    user = locate_user(email=email) # load up any existing user with this email address from the database
    # check whether the password the user entered matches the hashed password in the database
    if user and check_password_hash(user.data['password'], password):
        flask_login.login_user(user) # log in the user using flask-login
        flash('Welcome back, {}!'.format(user.data['email'])) # flash can be used to pass a special message to the template we are about to render
        return redirect(url_for('open_pack'))
    # else
    return 'Login failed'

# route to logout a user
@app.route('/logout')
def logout():
    flask_login.logout_user()
    flash('You have been logged out.  Bye bye!') # pass a special message to the template
    return redirect(url_for('home')) # redirect the user to the home page

# example of a route that requires the user to be logged in to access
@app.route('/protected')
@flask_login.login_required
def protected():
    current_user = flask_login.current_user
    return 'You are logged in as user {email}. Welcome!'.format(email=current_user.data['email'])

# route to handle any errors
@app.errorhandler(Exception)
def handle_error(e):
    """
    Output any errors - good for debugging.
    """
    return render_template('error.html', error=e) # render the edit template


# run the app
if __name__ == "__main__":
    #import logging
    #logging.basicConfig(filename='/home/ak8257/error.log',level=logging.DEBUG)
    app.run(debug = True)
