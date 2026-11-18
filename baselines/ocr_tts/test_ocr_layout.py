import unittest
from ocr_layout import layout_summary


def data_for(lines):
    data={k:[] for k in ('text','left','top','width','height','conf')}
    # Deliberately reverse input order: association must use coordinates, not OCR sequence.
    for text,x,y,h in reversed(lines):
        for word in text.split():
            width=len(word)*h*.55
            for key,value in dict(text=word,left=x,top=y,width=width,height=h,conf=95).items():data[key].append(value)
            x+=width+h*.4
    return data


class LayoutTests(unittest.TestCase):
    def test_name_and_strength_associate_across_form_line(self):
        summary,status=layout_summary(data_for([('NDC 62584-266-01',10,0,12),('Metoprolol Tartrate',10,40,25),('Tablets USP',10,80,18),('50 mg',10,110,30)]))
        self.assertEqual(summary,'Metoprolol Tartrate, 50 mg')
        self.assertEqual(status,'fields_extracted')
    def test_two_identical_labels_are_deduplicated(self):
        summary,status=layout_summary(data_for([('Metoprolol Tartrate',10,10,25),('50 mg',10,55,25),('Metoprolol Tartrate',10,300,25),('50 mg',10,345,25)]))
        self.assertEqual(summary,'Metoprolol Tartrate, 50 mg')
    def test_conflicting_strengths_do_not_choose_arbitrarily(self):
        summary,status=layout_summary(data_for([('Example Medicine',10,10,25),('50 mg',10,55,25),('Example Medicine',10,300,25),('100 mg',10,345,25)]))
        self.assertEqual(summary,'')
        self.assertEqual(status,'multiple_field_pairs')
    def test_unrelated_neighbor_column_is_not_used(self):
        summary,status=layout_summary(data_for([('Example Medicine',600,10,25),('50 mg',10,55,25)]))
        self.assertEqual(summary,'')
    def test_equivalent_and_elemental_detail_strengths_are_not_package_fields(self):
        summary,status=layout_summary(data_for([
            ('Calcium Carbonate 500 mg',10,10,25),
            ('elemental calcium 200 mg',10,200,18),
            ('equivalent to 220 mg calcium salt',10,240,18)]))
        self.assertEqual(summary,'Calcium Carbonate, 500 mg')
        self.assertEqual(status,'fields_extracted')

if __name__=='__main__':unittest.main()
