import datetime
import logging

from google.appengine.ext import db

import paypal
import settings

class Profile( db.Model ):
  owner = db.UserProperty()

  preapproval_amount = db.IntegerProperty() # cents
  preapproval_expiry = db.DateTimeProperty()
  preapproval_key = db.StringProperty()

  goal_active = db.BooleanProperty()
  goal_name = db.StringProperty()
  goal_count = db.IntegerProperty()
  goal_date = db.DateTimeProperty()

  current_count = db.IntegerProperty()

  words = db.TextProperty()

  def amount_dollars( self ):
    return self.preapproval_amount / 100

  @staticmethod
  def find( user ):
    profile = Profile.all().filter( 'owner =', user ).get()
    if profile == None:
      profile = Profile( owner=user, preapproval_amount=0, current_count=0, goal_active=False, words="" )
      profile.save()
    return profile

  @staticmethod
  def check_expired():
    candidates = Profile.all().filter( 'goal_active =', True ).filter( 'goal_date <', datetime.datetime.now() )
    total = 0
    failed = 0
    for candidate in candidates:
      if candidate.current_count < candidate.goal_count: # didn't make it
        failed += 1
        # take preapproval amount
        logging.info( "settling transaction..." )
        pay = paypal.PayWithPreapproval( amount=candidate.amount_dollars(), preapproval_key=candidate.preapproval_key )
        if pay.status() == 'COMPLETED':
          logging.info( "settling transaction: done" )
        else:
          logging.info( "settling transaction: failed" )

      candidate.goal_active = False      
      candidate.save()
      total += 1

    return ( failed, total )


class Preapproval( db.Model ):
  '''track interaction with paypal'''
  user = db.UserProperty()
  created = db.DateTimeProperty(auto_now_add=True)
  status = db.StringProperty( choices=( 'NEW', 'CREATED', 'ERROR', 'CANCELLED', 'COMPLETED' ) )
  status_detail = db.StringProperty()
  secret = db.StringProperty() # to verify return_url
  debug_request = db.TextProperty()
  debug_response = db.TextProperty()
  preapproval_key = db.StringProperty()
  amount = db.IntegerProperty() # cents

