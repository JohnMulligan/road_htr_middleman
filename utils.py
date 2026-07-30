import requests
import json
from localsettings import *
import re
import os
import time

import pickle

def uri_to_pagenum(uri):
	if uri is not None:
		try:
			pagenum=int(re.search("[0-9]+$",uri).group(0))
		except:
			pagenum=None
	else:
		pagenum=None
	return pagenum
	
	

def login():
	print('authenticating...')
	r=requests.post(
		url="http://192.168.1.109:8010/api/token/",
		json={
			'username':username,
			'password':password
		}
	)
	if r.status_code==200:
		print('successfully re-authenticated')
		j=r.json()
		access_token=j['access']
		refresh_token=j['refresh']
		headers['Authorization']=f'Bearer {access_token}'
	else:
		print('error:',r.content)
		access_token,refresh_token=None
	
	return access_token,refresh_token


def basic_requests(url,method='GET',data=None):
	
	if method in ['POST','PUT','PATCH','UPDATE']:
		r=requests.request(method,url,data=data,headers=headers)
	elif method=='GET':
		r=requests.get(url,headers=headers)
	
	if r.status_code in [401,403]:
		print("logging back in....")
		login()
		r=basic_requests(url,method=method,data=data)
	if r.status_code==200:
		return r
	else:
		print(r.__dict__)
		return None

def get_recent_events():
	url='http://192.168.1.109:8010/api/events/recent/'
	return basic_requests(url)

def get_recently_completed_assignments_page(page=None):
	if page is not None:
		url=f'http://192.168.1.109:8010/api/assignments/completed/?ordering=-completed_at&page={page}'
	else:
		url='http://192.168.1.109:8010/api/assignments/completed/?ordering=-completed_at'
	return basic_requests(url)
	
def get_image_annotations(image_id):
	url=f'http://192.168.1.109:8010/api/annotations/?image={image_id}'
	return basic_requests(url)

def get_image_obj(image_id):
	url=f'http://192.168.1.109:8010/api/image/{image_id}/'
	return basic_requests(url)

def get_image_data(url):
	r=requests.get(url)
	if r.status_code==200:
		return r.content
	else:
		print(r.__dict__)
		return None
	
def get_assignees(rca):
	primary_assignee=rca['assigned_to_name']
# 	secondary_assignees=[sa['username'] for sa in rca['support_agents']]
# 	assignees=primary_assignee+secondary+assignees
	return primary_assignee

def get_annotations(image_id):
	url=f'http://192.168.1.109:8010/api/annotations/?image={image_id}'
	resp=basic_requests(url)
	if resp is not None:
		text_content=' \n'.join([annotation['text_content'] for annotation in resp.json])
		annotation_count=len(resp)
		return text_content,annotation_count
	else:
		return None


def get_assignments():
	
	url=f'http://192.168.1.109:8010/api/assignments/'
	results=[]
	c=0
	while True:
		print("fetching",url)
		resp=basic_requests(url)
		if resp is not None:
			page_results=resp.json['results']
			results += page_results
			url=resp.json['next']
			if not url:
				break
# 			c+=1
# 			if c>5:
# 				break
	return results


def load_dumps():
	rows={}
	dumps=[f for f in os.listdir('dumps') if re.match('dump.*json',f)]
	for dump in dumps:
		d=open(os.path.join('dumps',dump),'r')
		t=d.read()
		d.close()
		try:
			j=json.loads(t)
			for k in j:
				rows[k]=j[k]
		except:
			pass
	return rows

def dump_rows(rows_dict):
	d=open('dumps/dump.json','w')
	d.write(json.dumps(rows_dict))
	d.close()



def pull_and_pickle_assignments():
	assignments=get_assignments()
	records={assignment['id']:assignment for assignment in assignments}
	with open(f"{str(int(time.time()))}.pkl", 'wb') as file:
		pickle.dump(records, file)


def analyze_pickles():
	pickles=[f for f in os.listdir('.') if not f.startswith('.') and f.endswith('.pkl')]
	pickle_integers




if __name__ == "__main__":
	pull_and_pickle_assignments()
	
	
	
# 	
# 	
# 	
# 	for assignment in assignments:
# 		record={
# 			'status':assignment['status']['label'],
# 			'id':assignment['id'],
# 			'assignee':assignment['assigned_to_name'],
# 			'page_name':assignment['target_display']
# 		}
# 		records.append(record)
# 	df=pd.DataFrame.from_records(records)
# 	print(df)