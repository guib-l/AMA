import os
import sys

import numpy as np


class Parser:
    
    def __init__( self, 
                  file_name:str,
                  comment:str = "",
                  verbose:bool = False,
                  replace:float=None,
                  init=True):
        """
        Parser class to read a file and extract data from it.
        Parameters
        ----------
        file_name : str
            The name of the file to read.
        comment : str
            A comment to be added to the file.
        verbose : bool
            If True, print debug information.
        replace : float
            The value to replace missing data with.
        init : bool
            If True, call the __call__ method to read the file.
        """

        self.file_name  = file_name
        self.comment    = comment
        self._verbose   = verbose
        self._data       = None
        
        if init:
            self.__call__(replace)

    @property
    def data(self,):
        try:
            return np.array(self._data)
        except:
            return self.data

    @data.setter
    def data(self, values):
        self._data = values

    def _compose(self, txt_block, replace=None):
        lst = []
        for lines in txt_block:
            if lines[0] != "#" :
                tmp = lines.rstrip('\n\r').split()
                for i in range(len(tmp)):
                    if tmp[i]=='':pass
                    else :
                        try:tmp[i]=float(tmp[i])
                        except:pass
                lst.append(tmp)

        row_lengths=[]
        for row in lst:
            row_lengths.append(len(row))
        max_length = max(row_lengths)

        for row in lst:
            while len(row) < max_length:
                row.append( replace )

        self.data = lst

    def __collect(self, replace=None):
        import time
        
        fichier = open(self.file_name, "r")
        assert fichier

        lst = []
        for lines in fichier:
            if lines[0] != "#" :
                tmp = lines.rstrip('\n\r').split()
                for i in range(len(tmp)):
                    if tmp[i]=='':pass
                    else :
                        try:tmp[i]=float(tmp[i])
                        except:pass
                lst.append(tmp)
        fichier.close()

        
        row_lengths=[]
        for row in lst:
            row_lengths.append(len(row))
        max_length = max(row_lengths)

        for row in lst:
            while len(row) < max_length:
                row.append( replace )

        self.data = lst


    def __collect_pd(self, replace=None):

        lst = []
        
        with open(self.file_name, "r") as fd:
            

            for lines in fd.readlines():
                
                if lines[0] == "#" : continue
                else:
                    tmp = lines.rstrip('\n\r').split()
                    try : lst.append(list(map(float,tmp)))
                    except: 
                        for i in range(len(tmp)):
                            try:tmp[i]=float(tmp[i])
                            except:pass
                        lst.append(tmp)
        
        row_lengths=[]
        for row in lst:
            row_lengths.append(len(row))
        max_length = max(row_lengths)

        for row in lst:
            while len(row) < max_length:
                row.append( replace )

        self.data = lst
        
    def print(self):
        if self.verbose == True:
            print("debug :: Les donnée sont issues du fichier {}"
                .format(self.file_name))
            print("debug :: Commentaire :: {}"
                .format(self.comment))
        else:
            print("Need to allow verbose variable")

    def extract(self, column_1):
        return np.array(self.data[:, column_1])

    def __call__(self, replace=None):
        self.__collect(replace=replace)
        if self._verbose == True:
            self.print()

    def write( self, 
               newFile:str = "", 
               comment:str = ""):
        
        assert len(self.data.shape)>2, \
            ValueError(f"data needs to be a tabel of 2 dimensions (given {len(self.data.shape)})")

        N = self.data.shape[0]
        M = self.data.shape[1]
        
        fw = open(newFile,"w")
        fw.write("# " + comment + "\n")
        for j in range(N):
            for i in range(M):
                fw.write("{}".format(self.data[i][j]))
                if i < M-1:fw.write("\t")
            fw.write("\n")
        return 0




