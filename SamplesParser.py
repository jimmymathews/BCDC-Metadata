#!/usr/bin/env python3

from os.path import isfile
import os
import os.path
from copy import deepcopy
import re
import pandas as pd
from Importer import Importer
from data_metamodel import *
from colors import *

class SamplesParser:
    def __init__(self, source_directory):
        i = Importer(source_directory)
        self.d = i.d
        self.dm = i.dm
        self.total_associated = 0

        from_carol_samples_file = 'inputs/Compiled_Q3.xlsx'
        self.parse_samples(from_carol_samples_file)

        # from_carol_exceptional_fmost = 'BICCN_2020Q1_fMOST.xlsx'
        # self.parse_samples(from_carol_exceptional_fmost, add=True)

    # def sanitize_entry(self, entry):
    #     if type(entry) == str:
    #         entry = re.sub('[\xa0]', '', entry)
    #         entry = re.sub('ftp://download\.brainimagelibrary\.org:8811', 'http://download.brainimagelibrary.org', entry)
    #         entry = re.sub('^\{(.*)\}$', '\\1', entry)
    #     return entry

    def check_additional_columns(self):
        extras = ['Prior Project', 'CORRECTED Anatomical Structure', 'Prior Anatomical Structure (CV)']
        for extra in extras:
            if not extra in self.samples.columns:
                self.samples[extra] = ''

    def parse_samples(self, samples_file, add=False):
        d = self.d
        self.samples = pd.read_excel(samples_file)
        # self.samples = self.samples.applymap(self.sanitize_entry)
        if add == True:
            self.check_additional_columns()
        given_handles = sorted(list(set(list(self.samples['Project (CV)']))))
        known_project_handles = list(d['Project'].entities.keys())
        known_collection_handles = list(d['Collection'].entities.keys())
        print('')
        print('Going through project names as provided in specimen manifest')
        for handle in given_handles:
            original_handle = handle
            if handle in self.special_breakout_cases():
                self.handle_special_case(handle)
                continue
            exceptional = self.parse_exceptional_handle(handle, verbose=True)
            if exceptional != None:
                handle = exceptional
            handle_proj = handle + '_proj'
            if handle in known_collection_handles:
                print(yellow + handle + reset + ' is a known ' + magenta + 'Collection' + reset + ' ' + green + bullet + reset)
                self.associate_collection_samples(handle, original_handle, add=add)
            elif handle_proj in known_project_handles:
                print(green + handle + reset + cyan + '_proj' + reset + ' is a known ' + magenta + 'Project' + reset + '. ', end='')
                c = self.check_single_collection(handle_proj)
                if not c:
                    print(red + 'But there are multiple collections in this project, so sample assignment is ambiguous. ' + bullet + reset)
                else:
                    print('Single collection ' + yellow + c.get_name() + reset + ' in this project. ' + green + bullet + reset)
                    self.associate_collection_samples(c.get_name(), original_handle, add=add)
            else:
                print(red + handle + reset + cyan + '_proj' + reset + ' is not in project list and ' + red + handle + reset +  ' is not in collection list. ' + red + bullet + reset)
            print()
        handle_projs = [handle + '_proj' for handle in given_handles]
        print('')
        print('Collection handles that are in database as part of BICCN, but not verbatim in samples file:')
        for handle in known_collection_handles:
            if not handle+'_proj' in handle_projs and not handle in given_handles:
                if not self.collection_is_part_of_program(d[handle], d['BICCN']):
                    continue
                message = ''
                print(cyan + handle.ljust(20) + reset + ' ' + message)
        print('')
        print('Associated so far: ' + green + str(self.total_associated) + reset + ', of ' + yellow + str(self.samples.shape[0]) + reset + ' samples in this round.')

    def special_breakout_cases(self):
        return ['zeng_tolias_pseq']

    def handle_special_case(self, handle):
        if not handle in self.special_breakout_cases():
            print(red + 'Error' + reset + ': ' + handle + ' not in the exception list.')
            exit()
        if handle == 'zeng_tolias_pseq':
            mts = {
                '_m' : {'Modality' : 'cell morphology', 'Technique' : 'neuron morphology reconstruction'},
                '_e' : {'Modality' : 'connectivity',    'Technique' : 'whole cell patch clamp'},
                '_t' : {'Modality' : 'transcriptomics', 'Technique' : 'SMART-seq v4'},
            }

            samples = self.samples
            pseq_samples = samples[samples['Project (CV)'] == handle]
            d = self.d
            tags = ['_m', '_e', '_t']
            archives = {'_m':'BIL', '_e':'DANDI', '_t':'NEMO'}
            collections = {}
            for tag in tags:
                collections[tag] = d[handle + tag]
                collections[tag].samples = pseq_samples.copy()
                collections[tag].samples.loc[:,'R24 Name (CV)'] = archives[tag]
                collections[tag].samples.loc[:,'Modality  (CV)'] = mts[tag]['Modality']
                collections[tag].samples.loc[:,'Technique  (CV)'] = mts[tag]['Technique']
            self.total_associated = self.total_associated + pseq_samples.shape[0]
            print(green + handle + reset + cyan + '_proj' + reset + ' is a known ' + magenta + 'Project' + reset + '. ')
            print('  Associated ' + green + '+'.join([str(collections[tag].samples.shape[0]) for tag in tags]) + reset + ' (same samples) samples to ' + yellow + ', '.join([collections[tag].get_name() for tag in tags]) + reset + ' (from \'' + handle + '\' in manifest)')
            print('')

    def associate_collection_samples(self, handle, handle_in_manifest, add=False):
        samples = self.samples
        collection_samples = samples[samples['Project (CV)'] == handle_in_manifest]
        d = self.d
        collection = d[handle]

        if add == False or not hasattr(collection, 'samples'):
            collection.samples = collection_samples
            print('  Associated ' + green + str(collection.samples.shape[0]) + reset + ' samples to ' + yellow + collection.get_name() + reset + ' (\'' + handle_in_manifest + '\' in manifest)')
        else:
            cached = deepcopy(collection.samples)
            collection_samples = collection_samples[cached.columns]
            collection.samples = pd.concat([cached, collection_samples])
            print('  Associated ' + green + str(collection_samples.shape[0]) + reset + ' *additional* samples to ' + yellow + collection.get_name() + reset + ' (\'' + handle_in_manifest + '\' in manifest) ' + '(had ' + str(cached.shape[0]) + ')')

        self.total_associated = self.total_associated + collection.samples.shape[0]

    def check_single_collection(self, handle_proj):
        d = self.d
        try:
            c = d[handle_proj]['has output']
            return c
        except MultipleResults:
            return False

    def exceptional_manifest_projects(self):
        explanations = {
            'yang_morf_confocal' : ['yang_MORF_confocal', 'Converting to mixedcase in order to match.'],
            'zeng_sc_10Xv2'      : ['zeng_sc_10xv2',      'Converting to lowercase in order to match.'],
            'zeng_sn_10Xv2'      : ['zeng_sn_10xv2',      'Converting to lowercase in order to match.'],
        }
        return explanations

    def parse_exceptional_handle(self, handle, verbose=False):
        explanations = self.exceptional_manifest_projects()
        if handle in explanations:
            if verbose:
                print('  Note: ' + magenta + explanations[handle][1] + reset + ' (' + handle + ')')
            return explanations[handle][0]
        else:
            return None

    def collection_is_part_of_program(self, collection, program):
        projects = [relation.get_source() for relation in collection.inverse_relations if relation.get_class_name() == 'has output']
        return any([self.project_is_part_of_program(project, program) for project in projects])

    def project_is_part_of_program(self, project, program):
        subprograms = self.list_of_targets(project, 'is part of')
        return any([self.subprogram_is_part_of_program(subprogram, program) for subprogram in subprograms])

    def subprogram_is_part_of_program(self, subprogram, program):
        actual_programs = self.list_of_targets(subprogram, 'is part of')
        return any([actual_program == program for actual_program in actual_programs])

    def list_of_targets(self, entity, relation_name, inverse=False):
        if not inverse:
            if not entity.r(relation_name) == None:
                return [relation.get_target() for relation in entity.r(relation_name).values()]
            else:
                return []
        else:
            return [relation.get_source() for relation in entity.inverse_relations.values() if relation.get_class_name() == relation_name]