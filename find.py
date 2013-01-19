from flask import Flask, render_template
import requests
import json
from requests.auth import HTTPDigestAuth
from time import sleep
import redis
import string

import json

r = redis.StrictRedis(host='localhost', port=6379, db=0)

app = Flask(__name__)

def make_req(url):
  print(url)
  sleep(0.1)
  return requests.get(url, auth=HTTPDigestAuth('hackathon', '179d50c6eb31188925926a5d1872e8117dc58572'))

def get_favorites(profileid):  
  resp = make_req('http://api.ru.istykker.dk/profile/'+profileid+'/favorites')
  favorites = resp.json()['favorites']
  favorite_ids = map(lambda f: f['id'], favorites)
  return filter(lambda f_id: f_id != profileid, favorite_ids)
  
def get_contacts(profileid):
  resp = make_req('http://api.ru.istykker.dk/profile/'+profileid+'/messages')
  resp_json = resp.json()
  if 'threads' in resp_json:
    threads = resp_json['threads']
    from_ids = map(lambda t: t['owningProfileId'], threads)
    to_ids = map(lambda t: t['targetProfileId'], threads)
    all_ids = set(from_ids+to_ids)
    return filter(lambda m_id: m_id != profileid, all_ids)

  return []

def get_contacts_thru_cache(profileid):
  if r.get('profile_contacts_cached:'+profileid)!='true':
    cids = get_contacts(profileid)
    for cid in cids:
      r.zadd('profile_contacts:'+profileid, 0, cid)
    r.set('profile_contacts_cached:'+profileid, 'true')
    return cids
  else:
    return r.zrange('profile_contacts:'+profileid, 0, -1)


def get_favorites_thru_cache(profileid):
  if r.get('profile_favorites_cached:'+profileid)!='true':
    cids = get_favorites(profileid)
    for cid in cids:
      r.zadd('profile_favorites:'+profileid, 0, cid)
    r.set('profile_favorites_cached:'+profileid, 'true')
    return cids
  else:
    return r.zrange('profile_favorites:'+profileid, 0, -1)

def get_profile(profileid):  
  return make_req('http://api.ru.istykker.dk/profile/'+profileid)

def get_name(profileid):
  profile_json = get_profile(profileid).json()['profile']
  givenName = profile_json.get('givenName')
  surname = profile_json.get('surName') 

  if givenName is not None:
    givenNameEnc = givenName.encode("utf-8")
  else:
    givenNameEnc = ''

  if surname is not None:
    surnameEnc = surname.encode("utf-8")
  else:
    surnameEnc = ''    

  return givenNameEnc + ' ' + surnameEnc

def get_name_thru_cache(profileid):
  cached = r.get('profile_name:'+profileid)
  if cached is None:
    cached = get_name(profileid)
    r.set('profile_name:'+profileid, cached)

  return cached

def add_node(profileid, nodes, edges, degrees, max_degrees):
  if profileid not in nodes:
    print("profile: "+profileid + " degree:"+str(degrees))
    name = get_name_thru_cache(profileid)
    nodes[profileid] = {'graphId':profileid, 'graphCaption':name}

    if degrees < max_degrees:
      contacts = get_contacts_thru_cache(profileid) + get_favorites_thru_cache(profileid)

      for contact_id in contacts:
        edges.append({'nodeAId':profileid, 'nodeBId':contact_id})
        add_node(contact_id, nodes, edges, degrees + 1, max_degrees)

@app.route("/<profileid>/<degrees>")
def profile(profileid, degrees):
  nodes = {}
  edges = []

  name=get_name_thru_cache(profileid)

  add_node(profileid, nodes, edges, 1, int(degrees))
  json_str = json.dumps({'nodes':nodes.values(),'edges':edges})
  next = '/'+profileid+'/'+str(int(degrees)+1)
  prev = '/'+profileid+'/'+str(int(degrees)-1)
  return render_template('graph.html', graph_json=json_str, prev=prev, next=next,name=name)

@app.route("/find/<profileid>")
def you_may_know(profileid):
  contacts = get_contacts_thru_cache(profileid)
  favorites = get_contacts_thru_cache(profileid)

  all_ids = set(contacts + favorites)
  known = set(all_ids)

  found = set()
  print(all_ids)
  for contact_id in all_ids:
    contact_ids = get_contacts_thru_cache(contact_id)
    favorite_ids = get_favorites_thru_cache(contact_id)
    unknown_ids = filter(lambda cid: cid not in known, contact_ids + favorite_ids)
    for u_id in unknown_ids:
      found.add(u_id)

  return json.dumps(map(lambda i: get_name_thru_cache(i), found))


if __name__ == "__main__":
  app.run(debug=True)
