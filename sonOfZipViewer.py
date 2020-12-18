import os
import re
import cv2
import sys
import math
import locale
import ntpath
import getopt
import zipfile
import pathlib
import natsort
import win32api
import subprocess
from copy import copy
from io import BytesIO
from contextlib import closing
from PIL import Image, ImageTk
from collections import namedtuple
from send2trash import send2trash

import tkinter as tk
from tkinter import ttk


class Zip_Viewer():

	def __init__(self, root, fileLoc):

		if root:
			self.main(root, fileLoc)
		else:
			root = self.createRoot()
			self.main(root, fileLoc)
			self.pictureWindow.bind('<Destroy>', self.exitForever)
			self.root.mainloop()


	def createRoot(self):
		root = tk.Tk()
		root.withdraw()
		return root


	def doMonitors(self):
		
		leftToRight = win32api.EnumDisplayMonitors()

		leftToRight.sort(key = lambda monitor: monitor[2][0])

		self.monitors = []
		self.gridSquare = []

		Monitor = namedtuple('Monitor', ['name', 'x', 'y', 'width', 'height', 'pixelSpan'])
		names = ['first', 'second', 'third', 'fourth', 'fifth', 'sixth']

		for i, monitor in enumerate(leftToRight):
			name = names[i]
			x = monitor[2][0]
			y = monitor[2][1]
			width = monitor[2][2] - monitor[2][0]
			height = monitor[2][3]
			pixelSpan = range(x, x + width)

			toAdd = Monitor(name, x, y, width, height, pixelSpan)

			self.monitors.append(toAdd)

		self.root.monitors = self.monitors


	def main(self, root, fileLoc):

		# for OS alphabetical file ordering
		locale.setlocale(locale.LC_ALL, "")

		self.root = root
		self.fileLoc = fileLoc

		path = os.path.dirname(os.path.realpath(self.fileLoc))
		self.baseDirectory = pathlib.Path(path)

		self.motion1Activated = False
		self.motion3Activated = False
		self.xPosition = 0
		self.yPosition = 0
		self.lastFileDeleted = ''

		self.pictureWindow = tk.Toplevel()
		
		self.sw = int(self.pictureWindow.winfo_screenwidth() // 1.05)
		self.sh = int(self.pictureWindow.winfo_screenheight() // 1.05)

		try:
			g = '+'.join(self.root.coordinates.split('+')[1:])
			thisX = int(g.split('+')[0])
		except:
			thisX = 60

		try:

			for monitor in self.root.root.monitors:
				if thisX in monitor.pixelSpan:
					self.xOrigin = monitor.x
					self.yOrigin = monitor.y
					break
		except:

			self.doMonitors()
			
			for monitor in self.root.monitors:
				if thisX in monitor.pixelSpan:
					self.xOrigin = monitor.x
					self.yOrigin = monitor.y
					break

		g = f'{self.sw}x{self.sh}+{self.xOrigin}+{self.yOrigin}'

		self.firstFile()

		self.pictureWindow.geometry(g)

		self.buttonBindings()

		self.pictureWindow.focus_force()


	def buttonBindings(self):

		self.pictureWindow.protocol('WM_DELETE_WINDOW', self._delete_window)
		self.pictureWindow.bind('<Destroy>', self._destroy_window)

		self.pictureWindow.bind('<Escape>', self.kill)
		self.pictureWindow.bind('<ButtonRelease-2>', self.kill)

		# rotate left and right for 1 and 2
		# mirror with 3

		self.pictureWindow.bind('<Delete>', self.deletePicture)
		self.pictureWindow.bind('<Control-z>', self.undoDelete)
		self.pictureWindow.bind('<Control-Shift-Delete>',
								lambda event: self.deletePicture(deleteFolder = True))

		self.pictureWindow.bind('o', self.openInExplorer)

		self.pictureWindow.bind('<ButtonRelease-3>', self.goLeft)
		self.pictureWindow.bind('<Left>', self.goLeft)
		self.pictureWindow.bind('<Control-Left>', self.goLeft100)
		self.pictureWindow.bind('<Shift-Left>', 
								lambda event: self.getNextFolder(-1))

		self.pictureWindow.bind('<ButtonRelease-1>', self.goRight)
		self.pictureWindow.bind('<Right>', self.goRight)
		self.pictureWindow.bind('<Control-Right>', self.goRight100)
		self.pictureWindow.bind('<Shift-Right>', 
								lambda event: self.getNextFolder(1))

		self.pictureWindow.bind('<MouseWheel>', self.interpretScroll)

		self.pictureWindow.bind('<B1-Motion>', self.moveImage)
		self.pictureWindow.bind('<B3-Motion>', self.zoomImage)

	
	def undoDelete(self, event=''):

		if not self.lastFileDeleted:
			return

		print(self.lastFileDeleted)


	def moveImage(self, event=''):

		if self.motion1Activated == False:
			self.motion1Activated = True
			self.initialX = event.x
			self.initialY = event.y
			return

		currentX = (self.initialX - event.x) // 4
		currentY = (self.initialY - event.y) // 4
		
		self.yPosition -= currentY
		self.xPosition -= currentX

		self.alterCurrentImage()


	def deletePicture(self, event='', deleteFolder = False):

		if not self.zipFileToRead:

			memberDeletion = self.currentMember

			deletionFile = self.baseDirectory / self.memberlist[memberDeletion]

			self.count -= 1

			del self.memberlist[memberDeletion]

			if deleteFolder:
				if self.directoryIndex == self.parentDirectorySize -1:
					self.getNextFolder(-1)
				else:
					self.getNextFolder(1)
			elif self.count == 0:
				deleteFolder = True
				self.getNextFolder(1)
			elif memberDeletion == self.count:
				self.currentMember -= 1

			self.displayNewImage()

			if deleteFolder:
				
				for file in os.listdir(str(deletionFile.parent)):
					
					if os.path.isdir(str(deletionFile.parent / file)):
						send2trash(str(deletionFile))
						self.lastFileDeleted = deletionFile
						return
				send2trash(str(deletionFile.parent))
				self.lastFileDeleted = deletionFile.parent
			else:
				send2trash(str(deletionFile))
				self.lastFileDeleted = deletionFile

		else:

			if deleteFolder:
				if self.directoryIndex == self.parentDirectorySize -1:
					self.getNextFolder(-1)
				else:
					self.getNextFolder(1)
				


	def zoomImage(self, event=''):

		if self.motion3Activated == False:
			self.motion3Activated = True
			self.initialX = event.x
			self.initialY = event.y
			return

		distance = math.dist([self.initialX, self.initialY], [event.x, event.y])

		if abs(self.initialX - event.x) > abs(self.initialY - event.y):
			if event.x < self.initialX:
				sign = 0
			else:
				sign = 1
		else:
			if event.y > self.initialY:
				sign = 0
			else:
				sign = 1


		if sign:
			self.currentZoom += distance / 1500
		else:
			self.currentZoom -= distance / 1500

		if self.currentZoom <= .05:
			self.currentZoom = .05
		elif self.currentZoom >= 3:
			self.currentZoom = 3
		
		self.alterCurrentImage()


	def alterCurrentImage(self):

		if self.currentZoom != 1:

			newWidth = int(self.originalImage.width * self.currentZoom)
			newHeight = int(self.originalImage.height * self.currentZoom)

			if newWidth == 0 or newHeight == 0:
				return

			self.image = self.originalImage.resize((newWidth, newHeight), Image.ANTIALIAS)
		
		self.label.place_forget()

		self.displayer = ImageTk.PhotoImage(self.image)

		self.label = tk.Label(self.pictureWindow, image=self.displayer)
		self.label.image = self.image
		self.label.place(y = self.yPosition, x = self.xPosition)


	def displayNewImage(self, firstgo = False):

		if not firstgo:
			self.label.place_forget()

		if self.zipFileToRead:
			zfiledata = BytesIO(self.zfile.read(self.memberlist[self.currentMember]))
		else:
			zfiledata = self.baseDirectory / self.memberlist[self.currentMember]

		self.originalImage = Image.open(zfiledata)

		if self.originalImage.width > self.originalImage.height:

			multiplier = self.sw / self.originalImage.width
			newHeight = int(self.originalImage.height * multiplier)

			self.image = self.originalImage.resize((self.sw, newHeight), Image.ANTIALIAS)
		
		else:
			
			multiplier = self.sh / self.originalImage.height
			newWidth = int(self.originalImage.width * multiplier)

			self.image = self.originalImage.resize((newWidth, self.sh), Image.BILINEAR)

		self.label = tk.Label()

		self.alterCurrentImage()
		
		self.pictureWindow.title(
			(
				f'{self.currentMember + 1} of {self.count}, '
				f'Directory {self.directoryIndex + 1} of {self.parentDirectorySize} | '
				f'{self.baseDirectory.name} | '
				f'{self.memberlist[self.currentMember]}'
			)
		)


	def interpretScroll(self, event):

		if event.delta != 0:
			self.yPosition += event.delta // 4
			self.displayNewImage()


	def exitForever(self, event=''):
		os._exit(1)


	def kill(self, event=''):

		self.pictureWindow.destroy()


	def _delete_window(self, event=''):

		try:
			self.pictureWindow.destroy()
			self.root.parent.focus_force()
		except:
			pass


	def _destroy_window(self, event=''):

		try:
			self.pictureWindow.destroy()
			self.root.parent.focus_force()
		except:
			pass


	def goLeft(self, event=''):

		if self.motion3Activated == True:
			self.motion3Activated = False
			return

		if self.currentMember <= 0:
			self.getNextFolder(-1)
			return
		else:
			self.currentMember -= 1

		self.displayNewImage()


	def goLeft100(self, event=''):

		if self.currentMember - 100 <= 0:
			self.currentMember = 0
		else:
			self.currentMember -= 100

		self.displayNewImage()


	def goRight(self, event=''):

		if self.motion1Activated == True:
			self.motion1Activated = False
			return

		if self.currentMember >= self.count - 1:
			self.getNextFolder(1)
		else:
			self.currentMember += 1

		self.displayNewImage()

	
	def openInExplorer(self, event = ''):

		if not self.zipFileToRead:

			self.currentFile = self.baseDirectory / self.memberlist[self.currentMember]

			subprocess.Popen(fR'explorer /select, "{self.currentFile}"')

		else:

			subprocess.Popen(fR'explorer /select, "{self.fileLoc}"')

	
	def parentDirectoryInfo(self):

		path = self.baseDirectory

		self.parentDirectory = os.listdir(self.baseDirectory.parent)

		self.parentDirectory = [
			i for i in self.parentDirectory if 
			os.path.isdir(f'{self.baseDirectory.parent}\\{i}'
			or i.endswith('.zip')
			)
		]

		#natsort.os_sorted(self.parentDirectory)

		#self.parentDirectory.sort(key=locale.strxfrm)

		self.parentDirectorySize = len(self.parentDirectory)
		self.directoryIndex = os.listdir(path.parent).index(path.name)
	

	def parentDirectoryZipInfo(self):

		path = self.baseDirectory
		fileLoc = pathlib.Path(self.fileLoc)

		print(self.baseDirectory)

		self.parentDirectory = os.listdir(self.baseDirectory)

		self.parentDirectory = [
			i for i in self.parentDirectory if 
			os.path.isdir(f'{self.baseDirectory.parent}\\{i}'
			or i.endswith('.zip')
			)
		]

		self.parentDirectorySize = len(self.parentDirectory)
		self.directoryIndex = os.listdir(path).index(fileLoc.name)


	def getNextFolder(self, direction = 1):

		path = self.baseDirectory

		if self.zipFileToRead:

			if self.directoryIndex + direction == -1:
				folderIndex = self.parentDirectorySize - 1
			else:
				folderIndex = self.directoryIndex + direction

			print(folderIndex)

			print(self.baseDirectory)
			self.baseDirectory = path.parent / self.\
							parentDirectory[folderIndex]


		if self.directoryIndex + direction == -1:
			folderIndex = self.parentDirectorySize - 1
		else:
			folderIndex = self.directoryIndex + direction

		print(folderIndex)

		self.baseDirectory = path.parent / self.\
							parentDirectory[folderIndex]

		self.currentMember = 0

		newFile = os.listdir(self.baseDirectory)[0]

		self.fileLoc = str(self.baseDirectory / newFile)

		self.firstFile()


	def goRight100(self, event=''):

		if self.currentMember + 100 >= self.count - 1:
			self.currentMember = self.count - 1
		else:
			self.currentMember += 100

		self.displayNewImage()


	def memberlistDirectory(self):

		self.zipFileToRead = False
			
		self.memberlist = os.listdir(self.baseDirectory)

		self.memberlist = [
			i for i in self.memberlist if os.path.isfile(f'{self.baseDirectory}\\{i}')
		]

		justFile = ntpath.basename(self.fileLoc)

		self.currentMember = self.memberlist.index(justFile)

		self.zfile = self.fileLoc

	
	def memberlistZip(self):
	
		self.zipFileToRead = True

		self.zfile = zipfile.ZipFile(self.fileLoc, 'r')
		self.memberlist = self.zfile.namelist()
		self.currentMember = 0

		self.memberlist = [
			i for i in self.memberlist if not i.endswith('/')
		]


	def firstFile(self):

		self.currentZoom = 1


		if self.fileLoc.endswith('.zip'): #or self.fileLoc.endswith('.rar'):

			self.parentDirectoryZipInfo()
			self.memberlistZip()

		else:

			self.parentDirectoryInfo()
			self.memberlistDirectory()

		self.count = len(self.memberlist)

		self.displayNewImage(firstgo = True)


if __name__ == "__main__":

	if len(sys.argv) == 2:
		Zip_Viewer(None, sys.argv[1])
