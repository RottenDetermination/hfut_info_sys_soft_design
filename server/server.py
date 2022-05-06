#    server.py  服务器，接收音频和视频
#    Copyright (C) 2022  梁国靖
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys
import socket
import threading
from cv2 import cv2
import numpy
import mysql.connector as mysql
import pyaudio
import wave
import msvcrt

class Server:
    def __init__(self):
        self.serverAddress = ('127.0.0.1', 6666)
        self.resolution = (640, 480)  # 分辨率
        self.img = ''
        self.key_video = '' # 视频秘钥
        self.send_video = bytes('send video', encoding="utf8")
        self.close_video = bytes('close video', encoding="utf8")

        self.chunk = 1024  # 每个缓冲区的帧数
        self.format = pyaudio.paInt16  # 采样位数
        self.channels = 1  # 单声道
        self.rate = 44100  # 采样频率
        self.key_audio = '' # 语音秘钥
        self.record_second = 1
        self.send_audio = bytes('send audio', encoding="utf8")
        self.close_audio = bytes('close audio', encoding="utf8")

    def connect(self):
        # 创建一个基于IPv4和TCP协议的Socket
        self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 服务器绑定端口，小于1024的端口号要管理员权限
        self.s.bind(self.serverAddress)
        # 监听端口，等待连接的最大数量为5
        self.s.listen(5)
        print('Waiting for connection...')
        while True:
            # 接受一个新连接:
            sock, addr = self.s.accept()
            # 创建新线程来处理TCP连接:
            t = threading.Thread(target=self.tcplink, args=(sock, addr))
            t.start()

    def tcplink(self, sock, addr):
        print('Accept new connection from %s:%s...' % addr)
        flag = sock.recv(128) # rev video or audio?

        if flag == self.send_video:
            # rev video
            # 创建VideoWriter类对象
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            video_encrypt = cv2.VideoWriter('%s_%s_video_encrypt.avi' % addr, fourcc, 5.0, (640, 480))
            video_decrypt = cv2.VideoWriter('%s_%s_video_decrypt.avi' % addr, fourcc, 5.0, (640, 480))
            while True:
                img_data = sock.recv(1920*1080)   # 每次接收的数据长度必须大于一帧图像大小
                if img_data == self.close_video:  # 客户端关闭连接
                    print('client shut down video')
                    break
                self.img = numpy.frombuffer(img_data, dtype='uint8')  # byte转为一维ndarray
                self.img = cv2.imdecode(self.img, 1)    # 解码
                self.img = cv2.resize(self.img, self.resolution) # resize分辨率
                cv2.imwrite("%s_%s_img_encrypt.png" % addr, self.img)
                video_encrypt.write(self.img) # 写入一帧
                self.__img_decrypt() # 图像解密
                cv2.imwrite("%s_%s_img_decrypt.png" % addr, self.img)
                cv2.imshow('%s_%s_img_decrypt.png' % addr, self.img)
                video_decrypt.write(self.img)  # 写入一帧

                key = cv2.waitKey(1)
                if key & 0xFF == ord('q'):  # 服务器关闭视频流
                    print('Server shut down video')
                    sock.send(self.close_video)
                    break
                else: # 继续接受视频
                    sock.send(self.send_video)
            video_encrypt.release()
            video_decrypt.release()
            cv2.destroyAllWindows()
            try:
                conn = mysql.connect(user='root', password='root', database='imgdb',
                                     auth_plugin='mysql_native_password')
                cursor = conn.cursor()
                values = ("%s_%s_video_encrypt.avi" % addr)
                cursor.execute("INSERT INTO video VALUES (null,\"%s\");" % values)
                conn.commit()
                cursor.close()
                conn.close()
            except mysql.Error as e:
                print("Error %d: %s" % (e.args[0], e.args[1]))
                sys.exit(0)

        if flag == self.send_audio:
            # rev audio
            wf = wave.open('%s_%s_audio_decrypt.wav' % addr, 'wb')  # 打开 wav 文件。
            wf.setnchannels(self.channels)  # 声道设置
            wf.setsampwidth(2)  # 采样位数设置
            wf.setframerate(self.rate)  # 采样频率设置
            wf_encrypt = wave.open('%s_%s_audio_encrypt.wav' % addr, 'wb')  # 打开 wav 文件。
            wf_encrypt.setnchannels(self.channels)  # 声道设置
            wf_encrypt.setsampwidth(2)  # 采样位数设置
            wf_encrypt.setframerate(self.rate)  # 采样频率设置
            while True :
                audio_data = sock.recv(4096)   # 每次接收的数据长度必须大于一帧图像大小
                wf_encrypt.writeframes(audio_data)  # 写入数据
                if audio_data == self.close_audio:  # 客户端关闭连接
                    print('client shut down audio')
                    break
                audio_data = numpy.frombuffer(audio_data, dtype='uint8')  # byte转为一维ndarray
                audio_data = audio_data ^ self.key_audio # 解密
                audio_data = audio_data.tobytes()
                wf.writeframes(audio_data)  # 写入数据
            wf.close()
            wf_encrypt.close()
            try:
                conn = mysql.connect(user='root', password='root', database='imgdb', auth_plugin='mysql_native_password')
                cursor = conn.cursor()
                values = ("%s_%s_audio_decrypt.wav" % addr)
                cursor.execute("INSERT INTO audio VALUES (null,\"%s\");" % values)
                conn.commit()
                cursor.close()
                conn.close()
            except mysql.Error as e:
                print("Error %d: %s" % (e.args[0], e.args[1]))
                sys.exit(0)

        sock.close()
        
    def key_video_init(self):
        # Logistic混沌序列加密参数
        x0 = 0.1
        u = 4
        height = self.resolution[1] # 480
        width = self.resolution[0] # 640
        self.key_video = numpy.zeros((height*width))
        self.key_video[0] = x0
        for i in range(0,height*width-1):
            self.key_video[i+1] = u*self.key_video[i]*(1-self.key_video[i])

        # 调整为[0,255]之间
        for i in range(0,height*width-1):
            self.key_video[i] = self.key_video[i]*255
            if self.key_video[i] > 255:
                self.key_video[i] = 255
            elif self.key_video[i] < 0:
                self.key_video[i] = 0
        # 转为uint8,图片是uint8
        self.key_video = self.key_video.astype(numpy.uint8)
        # 转为480*640 秘钥图像
        self.key_video = self.key_video.reshape(480,640)

    def key_audio_init(self):
        # Logistic混沌序列加密参数
        x0 = 0.1
        u = 4
        self.key_audio = numpy.zeros( self.chunk*2 )
        self.key_audio[0] = x0
        for i in range(0, self.chunk*2-1):
            self.key_audio[i + 1] = u * self.key_audio[i] * (1 - self.key_audio[i])

        # 调整为[0,255]之间
        for i in range(0, self.chunk*2-1):
            self.key_audio[i] = self.key_audio[i] * 255
            if self.key_audio[i] > 255:
                self.key_audio[i] = 255
            elif self.key_audio[i] < 0:
                self.key_audio[i] = 0
        # 转为uint8
        self.key_audio = self.key_audio.astype(numpy.uint8)

    def __img_decrypt(self):
        # 图像和秘钥异或运算
        for i in range(0,3):
            self.img[:, :, i] = cv2.bitwise_xor(self.img[:, :, i], self.key_video)
        
if __name__ == '__main__':
    server = Server()
    server.key_video_init()
    server.key_audio_init()
    server.connect()



