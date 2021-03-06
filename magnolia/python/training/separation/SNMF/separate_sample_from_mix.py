# Generic imports
import os
import json
import numpy as np
import pandas as pd
import librosa as lr

# Import sparse nmf function
from magnolia.factorization.snmf import SNMF

# Import utilities for using the model
from magnolia.utils.postprocessing import convert_preprocessing_parameters
from magnolia.features.preprocessing import undo_preprocessing
from magnolia.iterate.mix_iterator import MixIterator


def standardize_waveform(y):
    return (y - y.mean())/y.std()


def main():
    # from model settings
    params = {}
    params['cf'] = 'kl'
    params['sparsity'] = 5
    params['R'] = 1000
    params['conv_eps'] = 1e-3
    params['verbose'] = False
    T_L = 8
    T_R = 0
    random_seed = 1234567890
    uid_settings = '/local_data/magnolia/pipeline_data/date_2017_09_27_time_13_25/settings/assign_uids_LibriSpeech_UrbanSound8K.json'
    library_output_file = '/local_data/magnolia/experiment_data/date_2017_09_28_time_13_14/aux/model_saves/snmf/library_weights.hdf5'
    # library_output_file = '/local_data/magnolia/experiment_data/date_2017_09_28_time_13_14/aux/model_saves/snmf/REMOVE_library_weights.hdf5'

    params['max_iter'] = 25
    mixes = ['/local_data/magnolia/pipeline_data/date_2017_09_27_time_13_25/settings/mixing_LibriSpeech_UrbanSound8K_test_in_sample.json']
    from_disk = True
    mix_number = 1
    output_path = '/local_data/magnolia/experiment_data/date_2017_09_28_time_13_14/aux/sample_wav_files/snmf'


    os.makedirs(output_path, exist_ok=True)

    params['rng'] = np.random.RandomState(random_seed)

    mixer = MixIterator(mixes_settings_filenames=mixes,
                        batch_size=1,
                        from_disk=from_disk)

    # get frequency dimension
    frequency_dim = mixer.sample_dimensions()[0]

    # get number of sources
    settings = json.load(open(uid_settings))
    uid_file = settings['output_file']
    uid_csv = pd.read_csv(uid_file)
    number_of_sources = uid_csv['uid'].max() + 1

    model = SNMF(T_L, T_R, params['R'], params['sparsity'], params['cf'])

    model.load(library_output_file)

    assert(mix_number <= mixer.epoch_size())

    mix_settings = json.load(open(mixes[0]))

    signal = mix_settings['signals'][0]
    preprocessing_settings = json.load(open(signal['preprocessing_settings']))
    stft_args = preprocessing_settings['processing_parameters']['stft_args']
    istft_args = convert_preprocessing_parameters(stft_args)
    preemphasis_coeff = preprocessing_settings['processing_parameters']['preemphasis_coeff']
    n_fft = 2048
    if 'n_fft' in stft_args:
        n_fft = stft_args['n_fft']

    for i in range(mix_number):
        spec, bin_masks, source_specs, uids, snrs = next(mixer)

    spec = spec[0]
    bin_masks = bin_masks[0]
    source_specs = source_specs[0]
    uids = uids[0]
    snrs = snrs[0]

    print('SNR of this mix: {}'.format(snrs))

    y_mix = undo_preprocessing(spec, mixer.sample_length_in_bits(),
                               preemphasis_coeff=preemphasis_coeff,
                               istft_args=istft_args)

    # NOTE: this is only to make comparisons to the reconstructed waveforms later
    y_mix[-n_fft:] = 0.0
    y_mix = standardize_waveform(y_mix)

    lr.output.write_wav(os.path.join(output_path, 'mix_{}.wav'.format(mix_number)), y_mix, mixer.sample_rate(), norm=True)

    for i, source_spec in enumerate(source_specs):
        y = undo_preprocessing(source_spec, mixer.sample_length_in_bits(),
                               preemphasis_coeff=preemphasis_coeff,
                               istft_args=istft_args)

        # NOTE: this is only to make comparisons to the reconstructed waveforms later
        y[-n_fft:] = 0.0
        y = standardize_waveform(y)
        lr.output.write_wav(os.path.join(output_path, 'mix_{}_original_source_{}.wav'.format(mix_number, i + 1)), y, mixer.sample_rate(), norm=True)

    source_specs = model.source_separate(spec,
                                         max_iter=params['max_iter'],
                                         conv_eps=params['conv_eps'],
                                         rng=params['rng'],
                                         verbose=params['verbose'])

    for source_spec in source_specs:
        y = undo_preprocessing(source_specs[source_spec], mixer.sample_length_in_bits(),
                               preemphasis_coeff=preemphasis_coeff,
                               istft_args=istft_args)

        # NOTE: this is only because the masking creates a chirp in the last
        #       fft frame (likely due to the mask)
        y[-n_fft:] = 0.0
        y = standardize_waveform(y)
        lr.output.write_wav(os.path.join(output_path, 'mix_{}_separated_{}.wav'.format(mix_number, source_spec)), y, mixer.sample_rate(), norm=True)


if __name__ == '__main__':
    main()
