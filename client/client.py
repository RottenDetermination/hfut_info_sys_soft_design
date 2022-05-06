#    client.py  客户端，发送音频和视频
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
from cv2 import cv2
import time
import numpy
import msvcrt
import pyaudio
import wave

class Client:
    def __init__(self):
        self.serverAddress = ('127.0.0.1', 6666)
        self.resolution = (640, 480) # 分辨率
        self.img = '' # 摄像头捕捉一帧
        self.img_param = [int(cv2.IMWRITE_PNG_COMPRESSION), 0] # 设置传送图像格式、帧数
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
        # 建立连接:
        self.s.connect(self.serverAddress)

    def SenVideo(self):
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.s.send(self.send_video)  # tell server: send video
        # send video
        while True:
            time.sleep(0.1)

            if cv2.waitKey(1) & 0xFF == ord('q'):  # 客户端关闭视频流
                print('client shut down video')
                self.s.send(self.close_video)
                break

            ret, self.img = cap.read()    # get a frame,ndarray
            cv2.imshow("capture", self.img)
            self.img = cv2.resize(self.img, self.resolution)    # resize分辨率
            cv2.imwrite("img_decrypt.png" , self.img)
            self.__img_encrypt() # 图像加密
            cv2.imwrite("img_encrypt.png", self.img)
            ret, self.img = cv2.imencode('.png', self.img, self.img_param)  # 图片压缩编码为png,一维array
            img_data = self.img.tobytes()  # 矩阵转为bytes,socket只能传输bytes

            try:
                self.s.send(img_data)
            except Exception as err:
                print(err.args)
                cap.release()
                self.s.close()
                sys.exit(0)

            flag = self.s.recv(128) # 服务器发送send_video继续循环，close_video退出循环
            if flag == self.close_video: # 服务器关闭视频流
                print('Server shut down video')
                break

        cap.release()
        cv2.destroyAllWindows()  # 关闭视频窗口
        self.s.close()

    def SenAudio(self):
        # send audio
        self.s.send(self.send_audio)  # tell server: send audio

        p = pyaudio.PyAudio()  # 实例化对象
        stream = p.open(format=self.format,
                        channels=self.channels,
                        rate=self.rate,
                        input=True,
                        frames_per_buffer=self.chunk)  # 打开流，传入响应参数
        wf = wave.open('audio.wav', 'wb')  # 打开 wav 文件。
        wf.setnchannels(self.channels)  # 声道设置
        wf.setsampwidth(p.get_sample_size(self.format))  # 采样位数设置
        wf.setframerate(self.rate)  # 采样频率设置
        wf_encrypt = wave.open('audio_encrypt.wav', 'wb')  # 打开 wav 文件。
        wf_encrypt.setnchannels(self.channels)  # 声道设置
        wf_encrypt.setsampwidth(p.get_sample_size(self.format))  # 采样位数设置
        wf_encrypt.setframerate(self.rate)  # 采样频率设置
        # 采样位数16位，2字节，开2倍空间
        frames = numpy.zeros( self.chunk*2)
        frames = frames.astype(numpy.uint8)
        print('start record audio')
        while True:
            # time.sleep(0.1)

            if msvcrt.kbhit():
                if msvcrt.getch() == b'q':  # 客户端关闭音频流
                    print('client shut down audio')
                    self.s.send(self.close_audio)
                    break

            data = stream.read(self.chunk)
            wf.writeframes(data)  # 写入数据
            value = numpy.frombuffer(data, dtype=numpy.uint8) # bytes转为ndarray
            frames[0 : self.chunk*2-1] = value[0 : self.chunk*2-1]  # 需要缓冲一段时间
            audio_decrypt = frames ^ self.key_audio # 加密
            wf_encrypt.writeframes(audio_decrypt.tobytes())  # 写入数据
            self.s.send(audio_decrypt.tobytes())  # 矩阵转为bytes,socket只能传输bytes

        stream.stop_stream()  # 关闭流
        stream.close()
        p.terminate()
        wf.close()
        wf_encrypt.close()

        # 客户端关闭音频流
        self.s.send(self.close_audio)
        self.s.close()
        return

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
        self.key_video = self.key_video.reshape(480, 640)

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
    
    def __img_encrypt(self):
        # 图像和秘钥异或运算
        for i in range(0,3):
            self.img[:, :, i] = cv2.bitwise_xor(self.img[:, :, i], self.key_video)
        
if __name__ == '__main__':
    client = Client()
    client.key_video_init()
    client.key_audio_init()

    while True:
        key = msvcrt.getch()

        if key == b'v':
            print('client send video to to %s:%s.' % client.serverAddress)
            client.connect()
            client.SenVideo()
        elif key == b'a':
            print('client send audio to to %s:%s.' % client.serverAddress)
            client.connect()
            client.SenAudio()
        elif key == b'q':
            print('shut down client')
            break
