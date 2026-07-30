import requests

from localsettings import *
import re

from utils import login,basic_requests
import json
import time


def re_log_in():
	access_token,refresh_token=login()
	headers['Authorization']=f'Bearer {access_token}'
	print(headers)
	return headers


bad_assignments=[20580,20579,20578]

def get_incomplete_assignments():
	assignments_uri=f'{base_url}assignments/?assigned_to={agent_id}'
	
	assignments=[]
	while assignments_uri is not None:
		incomplete_assignments_page=basic_requests(assignments_uri)
		if incomplete_assignments_page:
			incomplete_assignments_page=incomplete_assignments_page.json()
		assignments_uri=incomplete_assignments_page['next']
		results=incomplete_assignments_page['results']
		assignments+=results
		print(f"found {len(assignments)} assignments")
		break
	
	incomplete_assignments=[a for a in assignments if
# 		a['status']['name']=='assigned' and
		a['id'] not in bad_assignments
	]
	
	print(f"counted {len(incomplete_assignments)}")
	
	return incomplete_assignments




def make_annotation_iiif_image_uri(annotation,image_base_uri):
	bounds=annotation['annotation_data']['target']['selector']['geometry']['bounds']
	minx=int(bounds['minX'])
	miny=int(bounds['minY'])
	maxx=int(bounds['maxX'])
	maxy=int(bounds['maxY'])
	w=maxx-minx
	h=maxy-miny
	uri=f'{image_base_uri}/{minx},{miny},{w},{h}/max/0/default.jpg'
	return uri


## initialize

def process_ia(ia):

	image_id=ia['object_id']
	assignment_id=ia['id']
	print('image id',image_id,'assignment id',assignment_id)
	ia_image_annotations=basic_requests(f'{base_url}annotations/?image={image_id}')
	print("annotations",ia_image_annotations)
	ia_image_trapp_data=basic_requests(f'{base_url}image/{image_id}/')
	print("imagedata",ia_image_trapp_data)
	if ia_image_trapp_data:
		ia_image_trapp_data=ia_image_trapp_data.json()
	image_base_uri=re.search('(.*?)(/full/.*)',ia_image_trapp_data['thumbnail_url']).group(1)
	if ia_image_annotations:
		ia_image_annotations=ia_image_annotations.json()
	
	for annotation in ia_image_annotations:
		print("annotation",annotation)
		annotation_iiif_image_uri=make_annotation_iiif_image_uri(annotation,image_base_uri)
		infer_headers={
			"Content-Type": "application/json"
		}
		payload={
			'hello':'world',
			'image_uri':annotation_iiif_image_uri
		}
		r=requests.post(infer_base_url,data=json.dumps(payload),headers=infer_headers)
		j=r.json()
		
		predicted_text=j['prediction']
		
		updated_annotation=annotation.copy()
		updated_annotation['text_content']=predicted_text
		body={
			"type": "TextualBody",
			"value": predicted_text,
			"purpose": "commenting"
		}
		
		updated_annotation['annotation_data']['bodies']=[body]
		
		annotation_id=annotation['id']
		patch_uri=f'{base_url}annotations/{annotation_id}/'
		
		
		r=requests.patch(patch_uri,data=json.dumps(updated_annotation),headers=headers)
		print(r.status_code,predicted_text)
	
	assignment_patch_payload={
		"status":"submitted_for_review",
		"content_type":10,
		"object_id":image_id
	}
	
	exit()
	
	assignment_patch_url=f'{base_url}assignments/{assignment_id}/'
	r=requests.patch(assignment_patch_url,data=json.dumps(assignment_patch_payload),headers=headers)
	print(r.status_code,"submitted assignment",assignment_id)
	

if __name__ == "__main__":
	
	incomplete_assignments=False
	sleep_factor=2
	while True:
		
		if incomplete_assignments:
			
			while incomplete_assignments:
				ia=incomplete_assignments.pop()
				remaining_ia_count=len(incomplete_assignments)
				print(f"{remaining_ia_count} assignments remaining")
				process_ia(ia)
			
			print("out of assignments. checking for more work...")
		else:
			print('fetching assignments')
			incomplete_assignments=get_incomplete_assignments()
			if len(incomplete_assignments)>0:
				sleep_factor=2
			else:
				sleep_factor**=2
		
		sleepy_time=2*sleep_factor
		print('sleeping for {sleepy_time} seconds')
	
	print("out of assignments.")
	


