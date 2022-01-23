#!/usr/bin/env python

# import debugpy
# print("Waiting for VSCode debugger...")
# debugpy.listen(5678)
# debugpy.wait_for_client()

##EKF imports
#from logging import exception
from re import X
#from statistics import geometric_mean
from ekf_python2.gaussparams_py2 import MultiVarGaussian
from ekf_python2.dynamicmodels_py2 import landmark_gate
from ekf_python2.measurementmodels_py2 import NED_range_bearing
from ekf_python2.ekf_py2 import EKF
#from importlib.metadata import distribution

#ekf_node_imports
from transform_to_world import transform_world_to_gate
from tf_pb_bc import tf_pb_bc

#Math imports
import numpy as np
import math
from scipy.spatial.transform import Rotation
from scipy.spatial.transform import Rotation as R

#ROS imports
import rospy
from vortex_msgs.msg import ObjectPosition
from geometry_msgs.msg import PoseStamped, TransformStamped
from nav_msgs.msg import Odometry
from tf.transformations import quaternion_from_euler
from tf.transformations import euler_from_quaternion
import tf2_ros
import tf2_py 

class EKFNode:
    ## gate state: x = [p_wg, theta_wg]
    

    def __init__(self):
        ##################
        ####EKF stuff####
        ##################

        # Geometric parameters
        self.rad2deg = 180 / np.pi
        self.deg2rad = np.pi / 180

        self.gate_prior = [0, 0] # z, roll, pitch of gate

        self.pb_bc = [0.3175, 0, - 0.10]
        self.euler_bc = [self.deg2rad*0.5, self.deg2rad*17.3, 0]

        self.gate_truth = []
        
        # Tuning parameters
        self.sigma_a = np.array([0.05, 0.05, 0.05, 0.05])
        self.sigma_z = np.array([0.5, 0.5, 0.5, 0.5])

        # Making gate model object
        self.gate_model = landmark_gate(self.sigma_a)

        #Gauss prev values

        self.x_hat0 = np.array([0, 0, 0, 0]) 
        self.P_hat0 = np.diag(self.sigma_z)
        self.prev_gauss = MultiVarGaussian(self.x_hat0, self.P_hat0)

        ################
        ###ROS stuff####
        ################

        # ROS node init
        rospy.init_node('ekf_vision')
        self.last_time = rospy.get_time()


        # Subscriber to gate pose and orientation #ToDo update the message type received from cv
        self.object_pose_sub = rospy.Subscriber('/object_detection/object_pose/gate', PoseStamped, self.obj_pose_callback, queue_size=1)
        self.obj_pose = 0
        self.obj_pose_prev = PoseStamped()

        # Subscriber to Odometry 
        self.odometry_sub = rospy.Subscriber('/odometry/filtered', Odometry, self.odometry_callback, queue_size=1)

        # Publisher #ToDo update the message type that autonomous wants (Vortex-AUV/vortex_msgs/msg/ObjectPosition.msg)
        self.gate_pose_pub = rospy.Publisher('/fsm/object_positions_in', ObjectPosition, queue_size=1)

        #Constant vector and rotation between body and camera
        body = 'auv/base_link' 
        cam_front = 'auv/camerafront_link'
        self.pb_bc = 0
        self.pb_bc, self.euler_bc = tf_pb_bc(body, cam_front)

        #Subscriber to gate truth
        #self.object_pose_truth_sub = rospy.Subscriber('/object_detection/object_pose/gate_truth', PoseStamped, self.obj_pose_truth_callback, queue_size=1)


    def get_Ts(self):
        Ts = rospy.get_time() - self.last_time
        return Ts
    
    def ekf_function(self, pw_wc, Rot_wb, z):

        measurement_model = NED_range_bearing(self.sigma_z, pw_wc, Rot_wb)

        Ts = self.get_Ts()

        my_ekf = EKF(self.gate_model, measurement_model)

        gauss_x_pred, gauss_z_pred, gauss_est = my_ekf.step_with_info(self.prev_gauss, z, Ts)
        
        self.last_time = rospy.get_time()
        self.prev_gauss = gauss_est # instantiate last estimate and time

        return gauss_x_pred, gauss_z_pred, gauss_est

    def est_to_pose(self, x_hat):
        x = x_hat[0]
        y = x_hat[1]
        z = x_hat[2]
        pos = [x, y, z]

        euler_angs = [self.gate_prior[0], self.gate_prior[1], x_hat[3]]

        return pos, euler_angs

    def transformbroadcast(self, parent_frame, pose):
        p = ObjectPosition()
        p = pose
        br = tf2_ros.TransformBroadcaster()
        t = TransformStamped()
        t.header.stamp = rospy.Time.now()
        t.header.frame_id = parent_frame
        t.child_frame_id = "object_"+str(p.objectID)
        t.transform.translation.x = p.objectPose.pose.position.x
        t.transform.translation.y = p.objectPose.pose.position.y
        t.transform.translation.z = p.objectPose.pose.position.z
        t.transform.rotation.x = p.objectPose.pose.orientation.x
        t.transform.rotation.y = p.objectPose.pose.orientation.y
        t.transform.rotation.z = p.objectPose.pose.orientation.z
        t.transform.rotation.w = p.objectPose.pose.orientation.w
        br.sendTransform(t)


    def obj_pose_callback(self, msg):
        self.obj_pose = PoseStamped()
        self.obj_pose = msg

    def obj_pose_truth_callback(self, msg):
        self.obj_pose_truth = PoseStamped()
        self.obj_pose_truth = msg

    def odometry_callback(self, msg):
        odom_pose = Odometry()
        odom_pose = msg
        
        if self.obj_pose == 0:
            ros_rate = 2.
            rospy.loginfo("No object pose recieved, will try again in " + str(ros_rate) + "seconds")
            rospy.sleep(ros_rate)
            pass
        else:   

            #Gate to camera publish
            obj_pose_position = np.array([self.obj_pose.pose.position.x, self.obj_pose.pose.position.y, self.obj_pose.pose.position.z])
            odom = np.array([msg.pose.pose.position.x, msg.pose.pose.position.y, msg.pose.pose.position.z])
            n_2 = np.random.normal(0, 0.2**2, 3)
            odom = odom + n_2

            odom_explicit_quat = [msg.pose.pose.orientation.x, msg.pose.pose.orientation.y, msg.pose.pose.orientation.z, msg.pose.pose.orientation.w]
            drone_orientation_euler = np.array(euler_from_quaternion(odom_explicit_quat))


            Rot_bc = R.from_euler('zyx', self.euler_bc)
            Rot_wb = R.from_euler('zyx', drone_orientation_euler)

            pc_cg = np.matmul(np.transpose(np.matmul(Rot_wb.as_dcm(), Rot_bc.as_dcm())),(obj_pose_position - odom)) #ground truth, odom
            #rospy.loginfo("#########################")
            rospy.loginfo("Camera_gate \n %s", pc_cg)
            #rospy.loginfo("New obj pose \n")
            #rospy.sleep(2.)

    
            self.obj_pose_prev = self.obj_pose 
            pw_wc, Rot_wc, z, Rot_wb, Rot_bc = transform_world_to_gate(odom_pose, pc_cg, self.pb_bc, self.euler_bc)

            #Do ekf here
            gauss_x_pred, gauss_z_pred, gauss_est = self.ekf_function(pw_wc, Rot_wc, z)
            x_hat = gauss_est.mean

            #EKF data pub
            ekf_position, ekf_pose = self.est_to_pose(x_hat)
            ekf_pose_quaterion = quaternion_from_euler(ekf_pose[0], ekf_pose[1], ekf_pose[2])

            p = ObjectPosition() 
            #p.pose.header[]
            p.objectID = self.obj_pose.header.frame_id
            p.objectPose.pose.position.x = ekf_position[0]
            p.objectPose.pose.position.y = ekf_position[1]
            p.objectPose.pose.position.z = ekf_position[2]
            p.objectPose.pose.orientation.x = ekf_pose_quaterion[0]
            p.objectPose.pose.orientation.y = ekf_pose_quaterion[1]
            p.objectPose.pose.orientation.z = ekf_pose_quaterion[2]
            p.objectPose.pose.orientation.w = ekf_pose_quaterion[3]
            rospy.loginfo("EKF Published: %s ", p)

            #Publish data
            self.gate_pose_pub.publish(p)
            #Transform between objects and odom
            self.transformbroadcast("auv/odom", p)
    




if __name__ == '__main__':
    try:
        ekf_vision = EKFNode()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
    