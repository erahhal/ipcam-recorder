#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import glob
import multiprocessing
import os
import re
import subprocess
import sys
import time

RECORDING_PATH = os.getcwd()
RECORDING_LENGTH_S = 300
MIN_FREE_DISK_KB = 200000
DATE_FORMAT = '%Y-%m-%d_%H-%M-%S'

"""
Config file format:

<camera1_name> <camera1_url>
<camera2_name> <camera2_url>
...
<cameraN_name> <cameraN_url>
"""

def get_free_space(path):
    df = subprocess.Popen(['df', path], stdout=subprocess.PIPE)
    output = df.communicate()[0].decode('utf-8')
    device, size, used, available, percent, mountpoint = output.split('\n')[1].split()
    available = int(available)
    return available

def record_stream(name, url):
    file_name = '{}_{}.mp4'.format(name, DATE_FORMAT)
    recording_length = str(RECORDING_LENGTH_S)
    rv = 0
    args = ['ffmpeg',
            # URL to record
            '-i', url,
            # Don't re-encode video, just copy raw data
            '-c:v', 'copy',
            # Re-encode audio into AAC codec, which is supported by MP4
            '-c:a', 'aac',
            # Select high-resolution stream
            '-map', '0',
            # Split recording into small files
            '-f', 'segment',
            # Set length of each segment
            '-segment_time', recording_length,
            # Write to mp4 format
            '-segment_format', 'mp4',
            # Start timestamp at 0 for each segment
            '-reset_timestamps', '1',
            # Use strftime function to name files
            '-strftime', '1',
            # Filename template
            file_name]
    try:
        print('Recording ' + name)
        rv = subprocess.call(args)
    except KeyboardInterrupt:
        print('Interrupt in process ' + name)
    finally:
        print('Cleaning up in process ' + name)
    return rv

def get_oldest_recording():
    p = re.compile('^.+_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}).mp4')
    oldest_filename = None
    oldest_timestamp = 9999999999999
    for filename in glob.glob('*.mp4'):
        result = p.search(filename)
        if result is not None:
            date_str = result.group(1)
            timestamp = time.mktime(datetime.datetime.strptime(date_str, DATE_FORMAT).timetuple())
            if timestamp < oldest_timestamp:
                oldest_timestamp = timestamp
                oldest_filename = filename
    return oldest_filename

def monitor_disk_space():
    try:
        while True:
            avail = get_free_space(RECORDING_PATH)
            if avail < MIN_FREE_DISK_KB:
                oldest_filename = get_oldest_recording()
                print('Disk space low.  Deleting oldest video recording: ' + oldest_filename)
                os.remove(oldest_filename)
            time.sleep(5)
    except KeyboardInterrupt:
        print('Interrupt in disk monitor process')
    finally:
        print('Cleaning up disk monitor process')

def checkfor(args):
    """Make sure that a program necessary for using this script is
    available.

    Arguments:
    args -- list of commands to pass to subprocess.call.
    """
    if isinstance(args, str):
        args = args.split()
    try:
        with open(os.devnull, 'w') as f:
            subprocess.call(args, stderr=subprocess.STDOUT, stdout=f)
    except:
        print('Required program "{}" not found! exiting.').format(args[0])
        sys.exit(1)

def main(argv):
    os.chdir(RECORDING_PATH)
    checkfor(['ffmpeg',  '-version'])
    filepath = 'cameras.config'
    processes = {}
    cameras = {}
    with open(filepath) as fp:
        while True:
            line = fp.readline()
            if not line:
                break
            line = line.strip()
            # ignore comments
            if len(line) and line[0] == '#':
                continue
            name, url = line.split()
            cameras[name] = url
    p = multiprocessing.Process(target=monitor_disk_space)
    p.start()
    processes[p.sentinel] = 'monitor'
    for name, url in cameras.items():
        p = multiprocessing.Process(target=record_stream, args=(name, url))
        p.start()
        processes[p.sentinel] = name

    try:
        from multiprocessing.connection import wait
        while True:
            sentinels = processes.keys()
            exited_sentinels = wait(sentinels)
            for sentinel in exited_sentinels:
                if processes[sentinel] == 'monitor':
                    del processes[sentinel]
                    p = multiprocessing.Process(target=monitor_disk_space)
                    p.start()
                    processes[p.sentinel] = 'monitor'
                else:
                    name = processes[sentinel]
                    del processes[sentinel]
                    url = cameras[name]
                    p = multiprocessing.Process(target=record_stream, args=(name, url))
                    p.start()
                    processes[p.sentinel] = name
    except KeyboardInterrupt:
        print('Interrupt in main')
    finally:
        print('Cleaning up in main')
        os.system('stty sane')

if __name__ == '__main__':
    main(sys.argv)
