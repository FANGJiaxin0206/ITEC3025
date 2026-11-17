import unittest
from unittest.mock import patch
from types import SimpleNamespace
from PIL import Image
from baseline import extract_text, orientation_score

class OrientationTests(unittest.TestCase):
    def test_confident_text_beats_unreadable_tokens(self):
        self.assertGreater(orientation_score({'text':['Metoprolol','50','mg'],'conf':[95,90,91]}),orientation_score({'text':['xwqzz','??'],'conf':[20,5]}))
    def test_all_directions_are_checked_before_extracting(self):
        confidence=iter([10,95,20,15]);images=[]
        def data(image,**kwargs):
            images.append(image.size)
            return {'text':['label'],'conf':[next(confidence)]}
        fake=SimpleNamespace(image_to_data=data,image_to_string=lambda image,**kwargs: str(image.size),Output=SimpleNamespace(DICT='dict'))
        with patch.dict('sys.modules',{'pytesseract':fake}):
            result=extract_text(Image.new('RGB',(100,50),'white'))
        self.assertEqual(len(images),4)
        self.assertEqual(result,str(images[1]))
    def test_no_confident_text_returns_empty(self):
        fake=SimpleNamespace(image_to_data=lambda *a,**k:{'text':[''],'conf':[-1]},Output=SimpleNamespace(DICT='dict'))
        with patch.dict('sys.modules',{'pytesseract':fake}):self.assertEqual(extract_text(Image.new('RGB',(10,10))), '')

if __name__=='__main__':unittest.main()
