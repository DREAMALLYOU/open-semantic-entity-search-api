import requests
import json
import sys

#
# Named Entity Linking, Disambiguation and Normalization by Named Entities in Solr search index
#
# Links plain text names/labels to ID/URI and normalize alias or alternate label to preferred label
#
# Queries are entity names as strings and/or plain text from which named entities will be extracted and can be scored by the context.
# Specification: https://github.com/OpenRefine/OpenRefine/wiki/Reconciliation-Service-API#query-request
#
# If no entity queries the entities will be extracted from the (con)text
#
# Returns Named Entities in Open Refine Reconciliation Service result format
# Specification: https://github.com/OpenRefine/OpenRefine/wiki/Reconciliation-Service-API#query-response

class Entity_Linker(object):

	solr = 'http://localhost:8983/solr/'
	solr_core = 'opensemanticsearch-entities'
	
	fields = [	'id',
				'score',
				'type_ss',
				'label_ss',
				'label_txt',
				'preferred_label_s',
				'preferred_label_txt',
				'skos_prefLabel_ss',
				'skos_prefLabel_txt',
				'skos_altLabel_ss',
				'skos_altLabel_txt',
				'skos_hiddenLabel_ss',
				'skos_hiddenLabel_txt'
	]

	verbose = False


	#
	# search entities by queries in entities index
	#
	def query_entities(self, queries, language=None, normalized_label_languages=['en'], text = None, limit=10000, normalized_entities = {}):

		normalized_entities = {}

		headers = {'content-type' : 'application/json'}

		for query in queries:

			params = {
				'wt': 'json',
				'defType': 'edismax',
				'qf': [	'label_ss',
						'label_txt',
						'preferred_label_s^10',
						'preferred_label_txt^5',
						'skos_prefLabel_ss^10',
						'skos_prefLabel_txt^5',
						'skos_altLabel_ss^2',
						'skos_altLabel_txt',
						'skos_hiddenLabel_ss^2',
						'skos_hiddenLabel_txt',
				],
				'fl': self.fields,
				'q': "\"" + queries[query]['query'] + "\"",
			}

			if 'limit' in queries[query]:
				params['rows'] = queries[query]['limit']
			else:
				params['rows'] = limit
			
			r = requests.get(self.solr + self.solr_core + '/select', params=params, headers=headers)

			if self.verbose:
				print ("Enity linker Solr result: {}".format(r.text))

			search_results = r.json()

			normalized_entities[query]={}
			normalized_entities[query]['result'] = []

			results = []

			for search_result in search_results['response']['docs']:

				label = None

				if 'preferred_label_s' in search_result:
					label = search_result['preferred_label_s']

				if not label:
					if 'skos_prefLabel_ss' in search_result:
						label = search_result['skos_prefLabel_ss'][0]

				if not label:
					if 'label_ss' in search_result:
						label = search_result['label_ss'][0]

				if not label:
					if 'skos_altLabel_ss' in search_result:
						label = search_result['skos_altLabel_ss'][0]

				if not label:
					label = search_result['id']

				types = []
				if 'type_ss' in search_result:
					types = search_result['type_ss']

				match = False
				for field in self.fields:
					if field in search_result:
						if not field == 'score':
	
							values = search_result[field]
							if not isinstance(values, list):
								values = [values]
	
							for value in values:
								if str(value).lower() == queries[query]['query'].lower():
									match = True
				
				result = {
					'id': search_result['id'],
					'name': label,
					'score': search_result['score'],
					'match': match,
					'type': types,
				}
				
				results.append(result)
				
			normalized_entities[query]['result'] = results

		return normalized_entities


	#
	# Extract entities from full text by matching labels in entity index
	# Extraction / tagging of labels in full text by Solr Text Tagger https://lucene.apache.org/solr/guide/7_4/the-tagger-handler.html
	#

	def dictionary_matcher(self, text, language=None, normalized_label_languages=['en'], limit=10000, tagger='all_labels_ss_tag', normalized_entities = {}, additional_result_fields={}):

		url = self.solr + self.solr_core + '/' + tagger

		fields = [	'id',
					'type_ss',
					'preferred_label_s',
					'skos_prefLabel_ss',
					'label_ss',
					'skos_altLabel_ss',
		]

		if additional_result_fields:
			fields.extend(additional_result_fields)

		params = {	'wt': 'json',
					'matchText': 'true',
					'overlaps': 'NO_SUB',
					'fl': ','.join(fields),
		}

		if limit:
			params['tagsLimit'] = str(limit)

		r = requests.post(url, data=text.encode('utf-8'), params=params)

		if self.verbose:
			print ("Entity linking / Solr Text Tagger result for tagger {}: {}".format(tagger, r.text))
		
		matches = r.json()

		i = 0
		for entity in matches['response']['docs']:

			label = None

			if 'preferred_label_s' in entity:
				label = entity['preferred_label_s']

			if not label:
				if 'skos_prefLabel_ss' in entity:
					label = entity['skos_prefLabel_ss'][0]

			if not label:
				if 'label_ss' in entity:
					label = entity['label_ss'][0]

			if not label:
				if 'skos_altLabel_ss' in entity:
					label = entity['skos_altLabel_ss'][0]

			if not label:
				label = entity['id']

			types = []
			if 'type_ss' in entity:
				types = entity['type_ss']
			
			result = {
				'id': entity['id'],
				'name': label,
				'match': True,
				'type': types,
			}

			if additional_result_fields:
				for field in additional_result_fields:
					if field in entity:
						result[field] = entity[field]

			normalized_entities[entity['id']] = {}
			normalized_entities[entity['id']]['result'] = [result]

		return normalized_entities

	#
	# get entities
	#

	def entities(self, queries=None, language=None, normalized_label_languages=['en'], text = None, limit=10000, taggers=['all_labels_ss_tag'], additional_result_fields={}):


		# if no entities queries, match entities from dictionary of labels from thesaurus, ontologies, databases and lists
		if queries:
			normalized_entities = self.query_entities(queries, language=language, normalized_label_languages=normalized_label_languages, text=text, limit=limit)
			
		else:

			# extract entities from full text by all taggers/stemmers in taggers parameter
			normalized_entities = {}
			for tagger in taggers:
				try:
					normalized_entities = self.dictionary_matcher(text=text, language=language, normalized_label_languages=normalized_label_languages, limit=limit, normalized_entities=normalized_entities, tagger=tagger, additional_result_fields=additional_result_fields)
				except BaseException as e:
					sys.stderr.write( "Exception using Solr Text Tagger {}: {}\n".format(tagger, e) )

		return normalized_entities
