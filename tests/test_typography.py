import unittest
from mediconfirm.text_format import readable_english
from mediconfirm.speech_tools import spoken_text
from mediconfirm.dialogue import Dialogue

class TypographyTests(unittest.TestCase):
 def test_contractions_and_negation(self):
  broken='I’ m sorry you’ re dizzy. I can’ t assess whether it’ s suitable.'
  fixed="I'm sorry you're dizzy. I can't assess whether it's suitable."
  self.assertEqual(readable_english(broken),fixed)
  self.assertEqual(spoken_text(broken),fixed)
 def test_comma_spacing_without_changing_numbers_or_paragraphs(self):
  text='Metoprolol Tartrate ,50 mg,one tablet. 1,000 units.\n\nKeep 0.5 mg.'
  self.assertEqual(readable_english(text),'Metoprolol Tartrate, 50 mg, one tablet. 1,000 units.\n\nKeep 0.5 mg.')
 def test_chinese_quotation_unchanged(self):
  self.assertEqual(readable_english('他说：“你好”，然后离开。'),'他说：“你好”，然后离开。')
 def test_returned_stored_and_spoken_reply_use_same_contractions(self):
  class Client:
   def request(self,messages):return 'You＇ re welcome. I canʼ t assess that.'
  chat=Dialogue();reply=chat.answer(Client(),'Hello','conversation',[],'',None)
  self.assertEqual(reply,"You're welcome. I can't assess that.")
  self.assertEqual(chat.messages[-1]['content'],reply)
