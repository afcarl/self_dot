import os
import time
import cPickle as pickle

from sklearn import preprocessing as pp
import numpy as np

from utils import net_rmse, filesize

def learn(state, mic, camera, brain):
    print 'LEARN PID', os.getpid()
    import Oger
    import mdp
    
    while True:
        if state['learn']:
            audio_data = mic.array()
            video_data = camera.array()

            mic.clear()
            camera.clear()

            scaler = pp.MinMaxScaler() 
            scaled_data = scaler.fit_transform(audio_data)

            reservoir = Oger.nodes.LeakyReservoirNode(output_dim=100, 
                                                      leak_rate=0.8, 
                                                      bias_scaling=.2, 
                                                      reset_states=True)
            readout = mdp.nodes.LinearRegressionNode(use_pinv=True)
            audio_net = mdp.hinet.FlowNode(reservoir + readout)

            x = scaled_data[:-1]
            y = scaled_data[1:]

            audio_net.train(x,y)

            reservoir = Oger.nodes.LeakyReservoirNode(output_dim=500,
                                                      leak_rate=0.8,
                                                      bias_scaling=.2,
                                                      reset_states=True)
            readout = mdp.nodes.LinearRegressionNode(use_pinv=True)
            video_net = mdp.hinet.FlowNode(reservoir + readout)

            # Video is sampled at a much lower frequency than audio.
            stride = audio_data.shape[0]/video_data.shape[0]
            x = scaled_data[scaled_data.shape[0] - stride*video_data.shape[0]::stride]
            y = video_data

            video_net.train(x,y)

            brain.append((audio_net, video_net, scaler))

            print 'Finished learning audio-video association'

            state['learn'] = False

        elif state['save']:
            pickle.dump(brain[:], file(state['save'], 'w'))
            print 'Brain saved as file {} ({})'.format(state['save'], filesize(state['save']))
            state['save'] = False

        elif state['load']:
            for element in pickle.load(file(state['load'], 'r')):
                brain.append(element)
            print 'Brain loaded from file {} ({})'.format(state['load'], filesize(state['load']))
            state['load'] = False

        else:
            time.sleep(.1)

            
def respond(state, mic, speaker, camera, projector, brain):
    print 'RESPOND PID', os.getpid()

    while True:
        if state['respond']:
            audio_data = mic.array()
            video_data = camera.array()

            mic.clear()
            camera.clear()

            rmse = net_rmse([ (net, scaler) for net,_,scaler in brain ], audio_data)

            print 'RMSE for neural networks in brain:', rmse
            audio_net, video_net, scaler = brain[np.argmin(rmse)]

            scaled_data = scaler.transform(audio_data)
            sound = audio_net(scaled_data)

            stride = audio_data.shape[0]/video_data.shape[0]
            projection = video_net(scaled_data[scaled_data.shape[0] - stride*video_data.shape[0]::stride]) 

            # Ordering to try to align video/sound 
            for row in projection:
                projector.append(row)

            for row in scaler.inverse_transform(sound):
                speaker.append(row)

            state['respond'] = False

        else:
            time.sleep(.1)
