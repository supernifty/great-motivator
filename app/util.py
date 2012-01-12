import logging
import random
import simplejson
import string

from google.appengine.api import channel
from google.appengine.api import users

import model

def random_alnum( count ):
  chars = string.letters + string.digits
  result = ''
  for i in range(count):
    result += random.choice(chars)
  return result

