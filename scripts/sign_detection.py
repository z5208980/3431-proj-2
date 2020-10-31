#!/usr/bin/env python

import os
import cv2
import numpy as np
from matplotlib import pyplot as plt
import rospy
from sensor_msgs.msg import CompressedImage, Image
from std_msgs.msg import UInt8
from cv_bridge import CvBridge

# Global maybe
#	Go: 1
# 	Stop: 2
from enum import Enum
turtlebot_state = Enum('state', 'go stop')


'''
Problems:
	- what todo after the bot has stopped.
	-
'''

class StopNode:
	def __init__(self):
		self.name = 'StopSignDetectNode ::'
		self.bridge = CvBridge()
		self.counter = 1
		self.sub = rospy.Subscriber('/raspicam_node/image/compressed', CompressedImage, self.stop_sign_detect_cb)
		self.pub_stop = rospy.Publisher('/detect/stop_sign', UInt8, queue_size=1)

	def stop_sign_detect_cb(self, frame):
		# debug from still image in assets
		# frame = cv2.imread("ros_stop.png")

		# Drop frame for processing speed (6ps)
		if self.counter % 3 != 0:
			self.counter += 1
			return
		else:
			self.counter = 1

		# frame = self.bridge.imgmsg_to_cv2(frame, "bgr8")	# raw
		frame_arr = np.fromstring(frame.data, np.uint8)
		frame = cv2.imdecode(frame_arr, cv2.IMREAD_COLOR)

		frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
		frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

		model = cv2.CascadeClassifier('stop_data.xml')

		# Use minSize because for not bothering with extra-small dots that would look like STOP signs
		found = model.detectMultiScale(frame_gray, minSize=(20, 20))
		n_stops = len(found)

		# visualisation of stop sign (for >= 1)
		if n_stops > 0:
			# DEBUG PURPOSES
			for (x, y, width, height) in found:
				cv2.rectangle(img_rgb, (x, y), (x + height, y + width), (0, 255, 0), 5)

			# Use this to stop the turtlebot
			pub_msg = UInt8()
			pub_msg.data = turtlebot_state.stop.value
			rospy.loginfo("%s RaspiCam detected Stop Sign", self.name)

		# plt.subplot(1, 1, 1)
		# plt.imshow(img_rgb)
		# plt.show()

	def main(self):
		rospy.loginfo("%s Spinning", self.name)
		rospy.spin()

if __name__ == '__main__': # sys.argv
	rospy.init_node('stop_sign')
	node = StopNode()
	node.main()