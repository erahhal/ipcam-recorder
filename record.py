#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import glob
import multiprocessing
import os
import pathlib
import queue
import re
import signal
import subprocess
import sys
import threading
import time

# Switch to script path
abspath = os.path.abspath(__file__)
dname = os.path.dirname(abspath)
os.chdir(dname)

RECORDING_PATH = os.getcwd()
RECORDING_LENGTH_S = 300
MIN_FREE_DISK_KB = 200000
FOLDER_DATE_FORMAT = '%Y-%m-%d'
FILE_DATE_FORMAT = '%Y-%m-%d_%H-%M-%S'

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
    _device, _size, _used, available, _percent, _mountpoint = output.split('\n')[1].split()
    available = int(available)
    return available

def record_stream(name, url):
    file_name = '{}/{}_{}.mp4'.format(FOLDER_DATE_FORMAT, name, FILE_DATE_FORMAT)
    recording_length = str(RECORDING_LENGTH_S)
    args = ['nohup',
            'ffmpeg',
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
    print('Recording ' + name)
    p = None
    try:
        def preexec():
            # seems to increase probability of leaving
            # behind an uncorrupted video, but not enough
            # data to know if this is actually having an effect
            os.setpgrp()
        p = subprocess.Popen(args,
                             preexec_fn=preexec,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             stdin=subprocess.DEVNULL,
                             universal_newlines=True)
        def sigterm_handler(signum, frame):
            os.kill(p.pid, signal.SIGINT)
        signal.signal(signal.SIGTERM, sigterm_handler)

        # Manage output using threads
        def enqueue_output(out, queue):
            for line in iter(out.readline, b''):
                queue.put(line)
            out.close()
        q_stdout = queue.Queue()
        t_stdout = threading.Thread(target=enqueue_output, args=(p.stdout, q_stdout))
        t_stdout.daemon = True
        t_stdout.start()
        q_stderr = queue.Queue()
        t_stderr = threading.Thread(target=enqueue_output, args=(p.stderr, q_stderr))
        t_stderr.daemon = True
        t_stderr.start()

        running = True
        while running:
            try:
                line = q_stdout.get_nowait()
                # Could print to a log
            except queue.Empty:
                # no output
                pass

            try:
                line = q_stderr.get_nowait()
                # Could print to a log
            except queue.Empty:
                # no output
                pass

            try:
                p.wait(timeout=3)
                running = False
            except subprocess.TimeoutExpired:
                # still running
                pass
    except KeyboardInterrupt:
        print('Interrupt in process ' + name)
        os.kill(p.pid, signal.SIGINT)
    finally:
        print('Cleaning up in process ' + name)

def monitor_folders():
    try:
        while True:
            now = datetime.datetime.today()
            folder_name = now.strftime('%Y-%m-%d')
            pathlib.Path(folder_name).mkdir(parents=True, exist_ok=True)
            if now.hour == 23 and now.minute > 54:
                # create folder for next day before ffmpeg has a chance to write
                next_day = now + datetime.timedelta(days=1)
                folder_name_next_day = next_day.strftime('%Y-%m-%d')
                pathlib.Path(folder_name_next_day).mkdir(parents=True, exist_ok=True)
            time.sleep(5)
    except KeyboardInterrupt:
        print('Interrupt in disk monitor process')
    finally:
        print('Cleaning up disk monitor process')

def get_oldest_recording():
    p = re.compile('^.+_(\\d{4}-\\d{2}-\\d{2}_\\d{2}-\\d{2}-\\d{2}).mp4')
    oldest_filename = None
    oldest_timestamp = 9999999999999
    for filename in glob.glob('**/*.mp4'):
        result = p.search(filename)
        if result is not None:
            date_str = result.group(1)
            timestamp = time.mktime(datetime.datetime.strptime(date_str, FILE_DATE_FORMAT).timetuple())
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
    processes[p.sentinel] = 'monitor_disk_space'
    p = multiprocessing.Process(target=monitor_folders)
    p.start()
    processes[p.sentinel] = 'monitor_folders'
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
                if processes[sentinel] == 'monitor_disk_space':
                    del processes[sentinel]
                    p = multiprocessing.Process(target=monitor_disk_space)
                    p.start()
                    processes[p.sentinel] = 'monitor'
                elif processes[sentinel] == 'monitor_folders':
                    del processes[sentinel]
                    p = multiprocessing.Process(target=monitor_folders)
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
