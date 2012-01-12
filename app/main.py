import cgi
import datetime
import decimal
import logging
import os
import random
import re
import simplejson

from google.appengine.api import channel
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext.webapp.util import run_wsgi_app

import model
import paypal
import settings
import util

class Home(webapp.RequestHandler):
  def get(self):
    '''initialize the main auction page'''
    # ensure logged in
    user = users.get_current_user()
    if not user:
      self.redirect(users.create_login_url(self.request.uri))
      return

    data = {
      'user': user,
      'profile': model.Profile.find(user),
    }
    path = os.path.join(os.path.dirname(__file__), 'templates/main.htm')
    self.response.out.write(template.render(path, data))

  def post(self):
    user = users.get_current_user()
    if not user:
      self.redirect(users.create_login_url(self.request.uri))

    profile = model.Profile.find( user ) 
    # count words
    words = self.request.get( "words" )
    count = len( re.split( '\s+', words ) )

    # add to words
    if profile.words == None:
      profile.words = ''
    profile.words += "<hr/>" + words
    if profile.current_count == None:
      profile.current_count = 0
    profile.current_count += count
    profile.save()

    path = os.path.join(os.path.dirname(__file__), 'templates/main.htm')
    self.response.out.write(template.render(path, { 'message': '%i words were added to your masterpiece' % count, 'user': user, 'profile': profile } ))

class Goal(webapp.RequestHandler):
  def get(self):
    user = users.get_current_user()
    if not user:
      self.redirect(users.create_login_url(self.request.uri))
    profile = model.Profile.find( user )
    data = { 'user': user, 'profile': profile }
    path = os.path.join(os.path.dirname(__file__), 'templates/goal.htm')
    self.response.out.write(template.render(path, data))

  def post(self):
    '''start preapproval'''
    user = users.get_current_user()
    if not user:
      self.redirect(users.create_login_url(self.request.uri))

    profile = model.Profile.find( user ) 

    # update goal details
    profile.goal_name = self.request.get( "name" )
    profile.goal_count = int(self.request.get( "count" )) 
    ( m, d, y ) = [ int( x ) for x in self.request.get( "date" ).split( '/' ) ]
    profile.goal_date = datetime.datetime( year=y, month=m, day=d )
    profile.save()

    amount = float(self.request.get( "amount" ))
    item = model.Preapproval( user=user, status="NEW", secret=util.random_alnum(16), amount=int(amount*100) )
    item.put()
    # get key
    preapproval = paypal.Preapproval(
      amount=amount,
      return_url="%s/success/%s/%s/" % ( self.request.uri, item.key(), item.secret ),
      cancel_url=self.request.uri,
      remote_address=self.request.remote_addr )

    item.debug_request = preapproval.raw_request
    item.debug_response = preapproval.raw_response
    item.put()

    if preapproval.status() == 'Success':
      item.status = 'CREATED'
      item.preapproval_key = preapproval.key()
      item.put()
      self.redirect( preapproval.next_url() ) # go to paypal
    else:
      item.status = 'ERROR'
      item.status_detail = 'Preapproval status was "%s"' % preapproval.status()
      item.put()

    path = os.path.join(os.path.dirname(__file__), 'templates/main.htm')
    self.response.out.write(template.render(path, { 'message': 'An error occurred connecting to PayPal', 'user': user, 'profile': profile } ))

class Success (webapp.RequestHandler):
  def get(self, key, secret):
    logging.info( "returned from paypal" )
    
    item = model.Preapproval.get( key )

    # validation
    if item == None: # no key
      self.error(404)
      return

    if item.status != 'CREATED':
      item.status_detail = 'Unexpected status %s' % item.status
      item.status = 'ERROR'
      item.put()
      self.error(501)
      return
      
    if item.secret != secret:
      item.status_detail = 'Incorrect secret %s' % secret
      item.status = 'ERROR'
      item.put()
      self.error(501)
      return

    # looks ok
    profile = model.Profile.find( item.user )
    profile.preapproval_amount = item.amount
    profile.preapproval_expiry = datetime.datetime.utcnow() + datetime.timedelta( days=settings.PREAPPROVAL_PERIOD )
    profile.preapproval_key = item.preapproval_key
    profile.goal_active = True
    profile.put()
    item.status = 'COMPLETED'
    item.put()
    
    path = os.path.join(os.path.dirname(__file__), 'templates/main.htm')
    self.response.out.write(template.render(path, { 'message': 'Your preapproved limit was updated.', 'user': item.user, 'profile': profile } ))

class Words(webapp.RequestHandler):
  def get(self):
    user = users.get_current_user()
    if not user:
      self.redirect(users.create_login_url(self.request.uri))
    profile = model.Profile.find( user )
    self.response.out.write( "<html><body>%s</body></html>" % profile.words )

class Check(webapp.RequestHandler):
  def get(self):
    # find active users which have expired
    ( failed, total ) = model.Profile.check_expired()

    path = os.path.join(os.path.dirname(__file__), 'templates/main.htm')
    self.response.out.write(template.render(path, { 'message': 'Payment was taken from %i users, from %i who finished.' % ( failed, total ) } ))

class NotFound (webapp.RequestHandler):
  def get(self):
    self.error(404)

application = webapp.WSGIApplication( [
    ('/', Home),
    ('/goal', Goal),
    ('/check', Check),
    ('/words', Words),
    ('/goal/success/([^/]*)/([^/]*)/.*', Success),
    ('/.*', NotFound),
  ],
  debug=True)

def main():
  logging.getLogger().setLevel(logging.DEBUG)
  run_wsgi_app(application)

if __name__ == "__main__":
  main()

