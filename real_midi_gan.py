# -*- coding: utf-8 -*-
"""real-midi-gan.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1KRkivpdUObb0h26xwJm33uvyaDzAsuQf
"""


from IPython import display
import time
from tensorflow.keras import layers
import os
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
import prep_data_back as pdata
from pathlib import Path
files = list(map(str, Path('datarecords').glob('*.tfrecords')))
dataset = pdata.get_dataset(files)
print(pdata.SONG_SHAPE)


TOTAL_OUTPUT_TIME_LENGTH = 32 * 48
SONG_SHAPE = pdata.SONG_SHAPE
# song[note_num][octave_num][time][0] == velocity
GENERATOR_INPUT_SHAPE = (512,)


def make_generator_model():
    model = tf.keras.Sequential()

    model.add(layers.Dense(48*256, input_shape=GENERATOR_INPUT_SHAPE,
                           use_bias=False,))
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())

    model.add(layers.Reshape((1, 2, 24, 256)))

    model.add(layers.Conv3DTranspose(192, (1, 2, 4),
                                     strides=(1, 1, 2),
                                     padding='same', use_bias=False))
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())
    print(model.output_shape)

    model.add(layers.Conv3DTranspose(128, (1, 2, 8),
                                     strides=(1, 1, 4),
                                     padding='same', use_bias=False))
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())
    print(model.output_shape)
    model.add(layers.Conv3DTranspose(64, (1, 2, 16),
                                     strides=(1, 1, 8),
                                     padding='same', use_bias=False))
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())
    print(model.output_shape)
    model.add(layers.Conv3DTranspose(32, (1, 5, 32),
                                     strides=(1, 2, 1),
                                     padding='valid', use_bias=False))
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())
    print(model.output_shape)
    model.add(layers.Conv3DTranspose(16, (6, 1, 64),
                                     strides=(1, 1, 1),
                                     padding='valid', use_bias=False))
    model.add(layers.BatchNormalization())
    model.add(layers.LeakyReLU())
    print(model.output_shape)
    model.add(layers.Conv3DTranspose(1, (6, 2, 64),
                                     strides=(2, 1, 1),
                                     padding='same', use_bias=False))
    print(model.output_shape)
    model.add(layers.Cropping3D(cropping=(0, 0, 47)))
    model.add(layers.ReLU())
    model.add(layers.Activation('tanh'))
    print(model.output_shape)
    assert model.output_shape[1:] == SONG_SHAPE
    return model

    return model


generator = make_generator_model()
noise = tf.random.normal([1, GENERATOR_INPUT_SHAPE[0]])
generated_image = generator(noise, training=False)


def make_discriminator_model():
    model = tf.keras.Sequential()

    # octave convolution
    model.add(layers.Conv3D(2, (1, 7, 1),
                            strides=(1, 1, 1),
                            padding='valid',
                            input_shape=SONG_SHAPE))
    model.add(layers.LeakyReLU())
    model.add(layers.Dropout(0.1))
    print(model.output_shape)
    # Note: None is the batch size
    assert model.output_shape == (None, 12, 1, TOTAL_OUTPUT_TIME_LENGTH, 2)

    # note distance convolution
    model.add(layers.Conv3D(8, (12, 1, 1),
                            strides=(1, 1, 1),
                            padding='same'))
    model.add(layers.LeakyReLU())
    model.add(layers.Dropout(0.1))
    print(model.output_shape)

    # small time convolution
    model.add(layers.Conv3D(64, (12, 1, 4),
                            strides=(1, 1, 2),
                            padding='valid'))
    model.add(layers.LeakyReLU())
    model.add(layers.Dropout(0.1))
    print(model.output_shape)
    # medium time convolution
    model.add(layers.Conv3D(128, (1, 1, 12),
                            strides=(1, 1, 4),
                            padding='valid'))
    model.add(layers.LeakyReLU())
    model.add(layers.Dropout(0.1))
    print(model.output_shape)
    # big time convolution
    model.add(layers.Conv3D(256, (1, 1, 48),
                            strides=(1, 1, 12),
                            padding='valid'))
    model.add(layers.LeakyReLU())
    model.add(layers.Dropout(0.1))
    print(model.output_shape)

#     # great time convolution
#     model.add(layers.Conv3D(512, (1, 1, 48),
#                             strides=(1, 1, 32),
#                             padding='valid'))
#     model.add(layers.LeakyReLU())
#     model.add(layers.Dropout(0.1))
#     print(model.output_shape)

    model.add(layers.Flatten())
    model.add(layers.Dense(1))

    return model


discriminator = make_discriminator_model()

# This method returns a helper function to compute cross entropy loss
cross_entropy = tf.keras.losses.BinaryCrossentropy(from_logits=True)


def discriminator_loss(real_output, fake_output):
    real_loss = cross_entropy(tf.ones_like(real_output), real_output)
    fake_loss = cross_entropy(tf.zeros_like(fake_output), fake_output)
    total_loss = real_loss + fake_loss
    return total_loss


def generator_loss(fake_output):
    return cross_entropy(tf.ones_like(fake_output), fake_output)


generator_optimizer = tf.keras.optimizers.Adam(1e-3)
discriminator_optimizer = tf.keras.optimizers.Adam(1e-4)

checkpoint_dir = './training_checkpoints'
checkpoint_prefix = os.path.join(checkpoint_dir, "ckpt")
checkpoint = tf.train.Checkpoint(generator_optimizer=generator_optimizer,
                                 discriminator_optimizer=discriminator_optimizer,
                                 generator=generator,
                                 discriminator=discriminator)

EPOCHS = 1000
num_examples_to_generate = 2
BATCH_SIZE = 64

# We will reuse this seed overtime (so it's easier)
# to visualize progress in the animated GIF)

seed = tf.random.normal([num_examples_to_generate, GENERATOR_INPUT_SHAPE[0]])

# Notice the use of `tf.function`
# This annotation causes the function to be "compiled".
@tf.function
def train_step(songs):
    noise = tf.random.normal([BATCH_SIZE, GENERATOR_INPUT_SHAPE[0]])

    with tf.GradientTape() as gen_tape, tf.GradientTape() as disc_tape:
        generated_songs = generator(noise, training=True)
        real_output = discriminator(songs, training=True)
        fake_output = discriminator(generated_songs, training=True)

        gen_loss = generator_loss(fake_output)
        disc_loss = discriminator_loss(real_output, fake_output)

    gradients_of_generator = gen_tape.gradient(
        gen_loss, generator.trainable_variables)
    gradients_of_discriminator = disc_tape.gradient(
        disc_loss, discriminator.trainable_variables)

    generator_optimizer.apply_gradients(
        zip(gradients_of_generator, generator.trainable_variables))
    discriminator_optimizer.apply_gradients(
        zip(gradients_of_discriminator, discriminator.trainable_variables))
    #print('gen_loss: {}, disc_loss: {}'.format(gen_loss, disc_loss))


def generate_and_save_images(model, epoch, test_input):
    # Notice `training` is set to False.
    # This is so all layers run in inference mode (batchnorm).
    predictions = model(test_input, training=False)
    for i, sample in enumerate(predictions):
        np.save('sample%d,%d.npy' % (epoch, i), sample.numpy())
    return

    fig = plt.figure(figsize=(4, 4))

    for i in range(predictions.shape[0]):
        plt.subplot(4, 4, i+1)
        plt.imshow(predictions[i, :, :, 0] * 127.5 + 127.5, cmap='gray')
        plt.axis('off')

    plt.savefig('image_at_epoch_{:04d}.png'.format(epoch))
    plt.show()


def train(dataset, epochs):
    for epoch in range(epochs):
        start = time.time()

        for i, song_batch in enumerate(dataset):
            print('\r%d / %d ...' % (i, 425), end='', flush=True)
            train_step(song_batch)
        print()

        # Save the model every 15 epochs
        if epoch % 15 == 0:
            checkpoint.save(file_prefix=checkpoint_prefix)
            # Produce images for the GIF as we go
            generate_and_save_images(generator,
                                     epoch,
                                     seed)

        print('Time for epoch {} is {} sec'.format(epoch, time.time()-start))

    # Generate after the final epoch
    display.clear_output(wait=True)
    generate_and_save_images(generator,
                             epochs,
                             seed)


train(dataset, EPOCHS)