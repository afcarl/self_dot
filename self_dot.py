#!/usr/bin/python
# -*- coding: latin-1 -*-

''' [self.]

@author: Axel Tidemann, �yvind Brandtsegg
@contact: axel.tidemann@gmail.com, obrandts@gmail.com
@license: GPL
'''

import multiprocessing as mp
import time

import zmq
from zmq.utils.jsonapi import dumps

import IO
import utils
import brain
import analyze_associations
import robocontrol

class Controller:
    def __init__(self, init_state):
        me = mp.current_process()
        print me.name, 'PID', me.pid

        self.state = init_state
        context = zmq.Context()
        self.publisher = context.socket(zmq.PUB)
        self.publisher.bind('tcp://*:{}'.format(IO.STATE))
        
        self.event = context.socket(zmq.PUB)
        self.event.bind('tcp://*:{}'.format(IO.EVENT))

        subscriber = context.socket(zmq.PULL)
        subscriber.bind('tcp://*:{}'.format(IO.EXTERNAL))

        snapshot = context.socket(zmq.ROUTER)
        snapshot.bind('tcp://*:{}'.format(IO.SNAPSHOT))

        print 'Communication channel listening on port {}'.format(IO.EXTERNAL)

        poller = zmq.Poller()
        poller.register(subscriber, zmq.POLLIN)
        poller.register(snapshot, zmq.POLLIN)

        while True:
            events = dict(poller.poll())

            if subscriber in events:
                self.parse(subscriber.recv_json())
                
            if snapshot in events:
                address, _, message = snapshot.recv_multipart()
                snapshot.send_multipart([ address, 
                                          b'',
                                          dumps(self.state) ])
                

    def parse(self, message):
        print '[self.] received:', message

        try:
            if 'register' in message and 'BRAIN' in message:
                _, name, free = message.split()
                self.state['brains'][name] = int(free)

            if 'fullscreen' in message:
                self.state['fullscreen'] = int(message[11:])

            if 'display2' in message:
                self.state['display2'] = int(message[9:])

            if message == 'startrec':
                self.state['record'] = True

            if message == 'stoprec':
                self.state['record'] = False

            if 'facerecognition' in message:
                _, value = message.split()
                self.state['facerecognition'] = value in ['True', '1']

            if 'memoryRecording' in message:
                self.state['memoryRecording'] = message[16:] in ['True', '1']

            if 'roboActive' in message:
                self.state['roboActive'] = int(message[11:])
                print self.state['roboActive']

            if 'decrement' in message:
                _, name = message.split()
                self.state['brains'][name] -= 1
                print '{} has now {} available slots'.format(name, self.state['brains'][name])

            if 'associate' in message:
                _, state = message.split()
                self.state['associate'] = state in ['True', '1']
                self.state['associate_learn'] = False
                                            
            if 'learnwav' in message:
                _, filename = message.split()
                if self.state['associate'] and not self.state['associate_learn']:
                    self.event.send_json({ 'setmarker': filename })
                    self.state['associate_learn'] = True
                else: 
                    d = self.state['brains']
                    winner = max(d, key=d.get)
                    print '{} chosen to learn, has {} available slots'.format(winner, self.state['brains'][winner])
                    self.event.send_json({ 'learn': winner, 'filename': filename })
                    self.state['associate_learn'] = False

            if 'respondwav' in message:
                _, filename = message.split()
                self.event.send_json({ 'respond': True, 'filename': filename })

            if message == 'setmarker':
                self.event.send_json({ 'setmarker': True })

            if 'autolearn' in message:
                self.state['autolearn'] = message[10:] in ['True', '1']

            if 'autorespond' in message:
                self.state['autorespond'] = message[12:] in ['True', '1']

            if 'inputLevel' in message:
                self.event.send_json({ 'inputLevel': message[11:] })

            if 'calibrateAudio' in message:
                self.event.send_json({ 'calibrateAudio': True })

            if 'csinstr' in message:
                self.event.send_json({ 'csinstr': message[8:] })
             
            if 'zerochannels' in message:
                self.event.send_json({ 'zerochannels': message[13:] })

            if 'playfile' in message:
                self.event.send_json({ 'playfile': message[9:] })

            if 'playfile_input' in message:
                self.event.send_json({ 'playfile_input': message[15:] })

            if 'playfile_primary' in message:
                self.event.send_json({ 'inputLevel': 'mute' }) # A bit ugly - Csound should mute itself, maybe?
                self.event.send_json({ 'playfile_primary': message[17:] })
                time.sleep(utils.wav_duration(message[17:]))
                self.event.send_json({ 'inputLevel': 'unmute' })

            if 'playfile_secondary' in message:
                self.event.send_json({ 'playfile_secondary': message[19:] })

            if 'selfvoice' in message:
                self.event.send_json({ 'selfvoice': message[10:] })

            if 'save' in message:
                self.event.send_json({ 'save': 'cns' if len(message) == 4 else message[5:] })

            if 'load' in message:
                self.event.send_json({ 'load': 'cns' if len(message) == 4 else message[5:] })

            self.publisher.send_json(self.state)

        except Exception as e:
            print 'Something went wrong when parsing the message - try again.'
            print e

if __name__ == '__main__':

    persistent_states = {'autolearn': False,
                         'autorespond': False,
                         'brains': {},
                         'record': False,
                         'memoryRecording': False,
                         'roboActive': False,
                         'fullscreen': 0,
                         'display2': 0,
                         'associate': False,
                         'associate_learn': False, 
                         'facerecognition': False}

    mp.Process(target=IO.audio, name='AUDIO').start() 
    mp.Process(target=IO.video, name='VIDEO').start()
    mp.Process(target=brain.face_extraction, args=('localhost',), name='FACE EXTRACTION').start()
    mp.Process(target=Controller, args=(persistent_states,), name='CONTROLLER').start()
    mp.Process(target=brain.classifier_brain, args=('localhost',)).start()
    mp.Process(target=analyze_associations.analyze, args=('localhost',), name='ANALYZE ASSOCIATIONS').start()
    mp.Process(target=robocontrol.robocontrol, args=('localhost',), name='ROBOCONTROL').start()

    try:
        raw_input('')
    except KeyboardInterrupt:
        map(lambda x: x.terminate(), mp.active_children())
