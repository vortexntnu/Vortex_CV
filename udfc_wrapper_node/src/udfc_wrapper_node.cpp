#include "udfc_wrapper_node/udfc_wrapper_node.hpp"
#include <opencv2/core/matx.hpp>
#include <iostream>



void readFromFile(){ //Cannot open the file. Think it is cmakelist fault.
    std::fstream newfile;
    std::vector<double> calibParams{};
    
    std::cout<<("Start loop")<<std::endl;
    newfile.open("1.txt",std::ios::in); //open a file to perform read operation using file object
    if(newfile.is_open()==false){
    std::cout<<("Could not open file.")<<std::endl; 
    }
    while(newfile.is_open()){ //checking whether the file is open
      std::string line;
    
      if(newfile.eof()){
        newfile.close();
        break;}
      newfile >> line;
      if((line != "[1080p]")&&(line.size()!=0)){
      line.erase(0,3);
      calibParams.push_back(stof(line));
      
      }
}
calibParams.pop_back();

}

void UDFCWrapperNode::getCameraMatrix(){
double fx{calibrationParams[0]};
double fy{calibrationParams[1]};
double cx{calibrationParams[2]};                      
double cy{calibrationParams[3]};

cv::Matx33f Matrix(fx, 0, cx,
          0, fy, cy,
          0, 0, 1);

CameraMatrix=Matrix;
}


void UDFCWrapperNode::getDistortionCoefficents(){
    double k1{calibrationParams[4]};
    double k2{calibrationParams[5]};
    distortionCoefficents = {k1,k2,0,0};
}




UDFCWrapperNode::UDFCWrapperNode(ros::NodeHandle nh)
{   
    getCameraMatrix();
    getDistortionCoefficents();

    image_raw_topic = "udfc/wrapper/camera_raw";
    image_rect_topic = "udfc/wrapper/camera_rect";
    ros_image_raw_publisher = nh.advertise<sensor_msgs::Image>(image_raw_topic,10);
    ros_image_rect_publisher = nh.advertise<sensor_msgs::Image>(image_rect_topic,10);
    camera_frame = "udfc";
    getCVImage();
}





void UDFCWrapperNode::getCVImage()
{   
    //readFromFile();

    //cv::namedWindow("Display window");
    
    cv::VideoCapture cap(_camera_id);
    if (!cap.isOpened())
    {
        std::cout << "cannot open camera"; // Needs to be changed to work with ROS
    }
    while (true){
        cap >> _cv_image;
        toImageRaw(_cv_image);
        toImageRect(_cv_image);
       // cv::Mat dst = _cv_image.clone();
       // cv::undistort(_cv_image,dst,CameraMatrix,distortionCoefficents);
       // cv::imshow("Display window", dst);
       // cv::waitKey(25);
    }
    cv::destroyAllWindows();
}

void UDFCWrapperNode::toImageRaw(cv::Mat cv_image)
{
    header.seq = counter_raw;
    counter_raw += 1;
    header.stamp = ros::Time::now();
    header.frame_id = camera_frame;
    img_bridge = cv_bridge::CvImage(header, sensor_msgs::image_encodings::BGR8, cv_image);
    img_bridge.toImageMsg(ros_image_raw);
    ros_image_raw_publisher.publish(ros_image_raw);
}

void UDFCWrapperNode::toImageRect(cv::Mat cv_image)
{   
    cv::Mat dst = _cv_image.clone();
    cv::undistort(_cv_image,dst,CameraMatrix,distortionCoefficents);
    header.seq = counter_rect;
    counter_rect += 1;
    header.stamp = ros::Time::now();
    header.frame_id = camera_frame;
    img_bridge = cv_bridge::CvImage(header, sensor_msgs::image_encodings::BGR8, dst);
    img_bridge.toImageMsg(ros_image_rect);
    ros_image_rect_publisher.publish(ros_image_rect);
}

int main(int argc, char **argv)
{   
    ros::init(argc, argv, "udfc_wrapper_node");
    ros::NodeHandle nh;
    UDFCWrapperNode wrapper(nh);
    ros::spin();

    return 0;
}