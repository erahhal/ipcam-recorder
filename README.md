# ipcam-recorder

### Config file format

Create a file named `cameras.config` containing the following:

    <camera1_name> <camera1_url>
    <camera2_name> <camera2_url>
    ...
    <cameraN_name> <cameraN_url>

You may need to add a username and password to the url, i.e.:

    camera1 rtsp://username:password@10.0.0.5/11

Then run:

    ./record.py

Currently this is only configurable by modifying `record.py`.
