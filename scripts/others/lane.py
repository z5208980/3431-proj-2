#!/usr/bin/env python

from __future__ import division
import rospy
import cv2
from cv_bridge import CvBridge
from sensor_msgs.msg import Image, CompressedImage
from std_msgs.msg import Float64

import numpy as np
import math

class LaneDetectNode():
	def __init__(self):
		self.name = "LaneDetectionNode ::"
		self.avgx = 0
		self.top_x = 250
		self.top_y = 5
		self.bottom_x = 250
		self.bottom_y = 239
		self.bridge = CvBridge()
		self.sub_lane = rospy.Subscriber('/raspicam_node/image/compressed', CompressedImage, self.detect_lane_cb, queue_size = 1)
		self.pub_image = rospy.Publisher('/lane_detect/image', Image, queue_size=1)
		self.pub_image_right = rospy.Publisher('/lane_detect/image/right', Image, queue_size=1)
		self.pub_image_left = rospy.Publisher('/lane_detect/image/left', Image, queue_size=1)
		self.pub_center = rospy.Publisher('/lane_detect/center', Float64, queue_size=1)

	# Calculate Cluster of lines in lanes
	def average_line(self, lines):
		if lines['n'] != 0:
			m = lines['slope']/lines['n']
			b = lines['intercept']/lines['n']
			# (Gradient, Y-Intercept)
			return (m, b)

		return None

	# Returns two point of given gradient and y-inter
	def get_points(self, m, b):
		x1 = 0
		x2 = 100000
		y1 = int(m*x1 + b)
		y2 = int(m*x2 + b)
		return (x1, y1), (x2, y2)

	# Gets the x-intercept
	def get_x_intercept(self, m, b):
		x, y = 0, 0
		if m != 0:
			x = (-b)/m
		return (x, y)

	# Frame Masking for Area of interest (lane in front of TurtleBot)
	def mask_lanes(self, frame, arr):
		mask = np.zeros_like(frame[:,:,0])
		polygon = np.array(arr)
		cv2.fillConvexPoly(mask, polygon, 1)
		frame = cv2.bitwise_and(frame,frame,mask=mask)

		return frame

	# Change (Like Bird Eye) perception of image
	def projected_perspective(self, frame):
		pts_src = np.array([
		[320 - self.top_x, 360 - self.top_y],
		[320 + self.top_x, 360 - self.top_y],
		[320 + self.bottom_x, 240 + self.bottom_y],
		[320 - self.bottom_x, 240 + self.bottom_y]])

		pts_dst = np.array([[200, 0], [800, 0], [800, 600], [200, 600]])
		h, status = cv2.findHomography(pts_src, pts_dst)
		frame = cv2.warpPerspective(frame, h, (1000, 600))
		frame = frame[0:897, 116:883]	# remove the black sides

		return frame

	# Original -> GrayScale -> Darken -> HLS -> Threshold -> Gaussian Blur -> Canny -> Hough
	def detect_lines(self, frame):
		frame_copy = frame.copy()
		frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) # GrayScale
		frame_hsl = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV) # HLS
		frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) # GrayScale

		# lower = np.array([106,0,155])
		# upper = np.array([173,26,201])
		# mask = cv2.inRange(frame_hsl, lower, upper)
		# frame_thres = cv2.bitwise_and(frame_hsl, frame_hsl, mask=mask) # Threshold (Mask)
		frame_gauss = cv2.GaussianBlur(frame_gray, (5,5), cv2.BORDER_DEFAULT) # Gaussian

		_, frame_filtered = cv2.threshold(frame_gauss, 133 ,255, cv2.THRESH_BINARY)
		frame_blur = cv2.GaussianBlur(frame_filtered, (5,5), cv2.BORDER_DEFAULT)

		v = np.median(frame)
		sigma = 0.33
		lower = int(max(0, (1.0 - sigma) * v))
		upper = int(min(255, (1.0 + sigma) * v))
		edges = cv2.Canny(frame_blur, lower, upper, apertureSize = 3) # Canny

		lines = cv2.HoughLines(edges, 0.8, np.pi/180, 80) # Hough

		line_image = np.zeros_like(frame)
		lane = { 'n': 0, 'slope': 0, 'intercept': 0 }
		if not lines is None:
			for line in lines:
				rho, theta = line[0][0], line[0][1]
				a, b = np.cos(theta), np.sin(theta)
				x0, y0 = a*rho, b*rho
				x1, y1 = int(x0 + 1000*(-b)), int(y0 + 1000*(a))
				x2, y2 = int(x0 - 1000*(-b)), int(y0 - 1000*(a))

				if x2 - x1 == 0:
					slope = 0
				else:
					slope = (y2 - y1) / (x2 - x1)

				intercept = y1 - (slope * x1)

				if -0.2 < slope and slope < 0.2:
					# cv2.line(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
					x = 0
				else:
					lane['n'] += 1
					lane['slope'] += slope
					lane['intercept'] += intercept
					cv2.line(frame, (x1, y1), (x2, y2), (255, 255, 255), 2)
					cv2.line(frame_copy, (x1, y1), (x2, y2), (255, 255, 255), 2)
					cv2.line(line_image, (x1, y1), (x2, y2), (255, 255, 255), 2)

		line_image = cv2.addWeighted(frame, 0.8, line_image, 1, 1)
		# cv2.line(frame, pt1, pt2, (255, 255, 255), 2)

		# heading_image = self.display_heading_line(frame, steering_angle)
		# mb[0], mb[1] = gradient, y-intercept
		mb = self.average_line(lane)
		if not mb is None:
			lane = { 'n': 1, 'slope': mb[0], 'intercept': mb[1] }
			# CvFrame, {nLane, gradient, intercept}
			return frame, lane
		return frame, None

	def detect_and_draw_lane(self, frame):
		frame_copy = frame.copy()	# Original

		height, width, channel = frame.shape
		frame_left = self.mask_lanes(frame_copy, [[0, 0], [int(width/2), 0], [int(width/2), height], [0, height]])
		frame_right = self.mask_lanes(frame_copy, [[int(width/2), 0], [width, 0], [width, height], [int(width/2), height]])

		frame_right_with_lines, right_lane = self.detect_lines(frame_right)
		frame_left_with_lines, left_lane = self.detect_lines(frame_left)
		# frame_left_with_lines, left_lane = None, None
		# frame_right_with_lines, right_lane = None, None
		# Used for Visualisation (Left and Right Lane Detection)

		if not right_lane is None:
			pt_r1, pt_r2 = self.get_points(right_lane['slope'], right_lane['intercept'])
			cv2.line(frame, pt_r1, pt_r2, (255, 255, 255), 2)
		img_msg = self.bridge.cv2_to_imgmsg(frame_right_with_lines, "bgr8")
		self.pub_image_right.publish(img_msg)

		if not left_lane is None:
			pt_l1, pt_l2 = self.get_points(left_lane['slope'], left_lane['intercept'])
			cv2.line(frame_left_with_lines, pt_l1, pt_l2, (2, 255, 255), 2)
		img_msg = self.bridge.cv2_to_imgmsg(frame_left_with_lines, "bgr8")
		self.pub_image_left.publish(img_msg)

		# Found Robot Line
		if not (right_lane and left_lane) is None: # If Left and Right Available (Average Out Lines)
			pt_r1, pt_r2 = self.get_points(right_lane['slope'], right_lane['intercept'])
			cv2.line(frame, pt_r1, pt_r2, (255, 255, 255), 2)
			pt_l1, pt_l2 = self.get_points(left_lane['slope'], left_lane['intercept'])
			cv2.line(frame, pt_l1, pt_l2, (0, 255, 255), 2)

			(rx, ry) = self.get_x_intercept(right_lane['slope'], right_lane['intercept'])
			(lx, ly) = self.get_x_intercept(left_lane['slope'], left_lane['intercept'])

			llines = self.make_points(frame, (right_lane['slope'], right_lane['intercept']))
			rlines = self.make_points(frame, (left_lane['slope'], left_lane['intercept']))
			self.avgx = int((rx + lx)/2)
			cv2.line(frame, (self.avgx,0), (self.avgx,height), (255, 0, 0), 2)

			lane_lines = [llines, rlines]
			steering_angle = self.get_steering_angle(frame_copy, lane_lines)
			msg_desired_center = Float64()
			msg_desired_center.data = steering_angle
			self.pub_center.publish(msg_desired_center)
		elif not left_lane is None: # If Left Available (LeftLaneHug)
			pt_r1, pt_r2 = self.get_points(left_lane['slope'], left_lane['intercept'])
			cv2.line(frame, pt_r1, pt_r2, (255, 255, 255), 2)
		else: # If None (TravelStraight or takest last known center)
			cv2.line(frame, (self.avgx,0), (self.avgx,height), (255, 0, 0), 2)
			pass

		# Publish center for controlNode

		return frame

	def make_points(self, frame, line):
		height, width, _ = frame.shape
		slope, intercept = line
		y1 = height  # bottom of the frame
		y2 = int(y1 / 2)  # make points from middle of the frame down

		if slope == 0:
			slope = 0.1

		x1 = int((y1 - intercept) / slope)
		x2 = int((y2 - intercept) / slope)
		return [x1, y1, x2, y2]

	def detect_lane_cb(self, frame):
		frame_arr = np.fromstring(frame.data, np.uint8)
		frame = cv2.imdecode(frame_arr, cv2.IMREAD_COLOR)
		frame = self.projected_perspective(frame)
		frame = self.detect_and_draw_lane(frame)
		img_msg = self.bridge.cv2_to_imgmsg(frame, "bgr8")
		self.pub_image.publish(img_msg)

	def display_heading_line(self, frame, steering_angle):
		heading_image = np.zeros_like(frame)
		height, width, _ = frame.shape

		steering_angle_radian = steering_angle / 180.0 * math.pi
		x1 = int(width / 2)
		y1 = height
		x2 = int(x1 - height / 2 / math.tan(steering_angle_radian))
		y2 = int(height / 2)

		cv2.line(heading_image, (x1, y1), (x2, y2), line_color, line_width)

		heading_image = cv2.addWeighted(frame, 0.8, heading_image, 1, 1)

		return heading_image

	def get_steering_angle(self, frame, lane_lines):
		height, width, _ = frame.shape
		x_offset, y_offset = 0, 1
		if len(lane_lines) == 2: # if two lane lines are detected
			_, _, left_x2, _= lane_lines[0] # extract left x2 from lane_lines array
			_, _, right_x2, _ = lane_lines[1] # extract right x2 from lane_lines array
			mid = int(width / 2)
			x_offset = (left_x2 + right_x2) / 2 - mid
			y_offset = int(height / 2)
		elif len(lane_lines) == 1: # if only one line is detected
			x1, _, x2, _ = lane_lines[0]
			x_offset = x2 - x1
			y_offset = int(height / 2)
		elif len(lane_lines) == 0: # if no line is detected
			x_offset = 0
			y_offset = int(height / 2)

		angle_to_mid_radian = math.atan(x_offset / y_offset)
		angle_to_mid_deg = int(angle_to_mid_radian * 180.0 / math.pi)
		steering_angle = angle_to_mid_deg + 90

		return steering_angle

	def main(self):
		rospy.loginfo("%s Spinning", self.name)
		rospy.spin()

if __name__ == '__main__': # sys.argv
	rospy.init_node('detect_lane')
	node = LaneDetectNode()
	node.main()
