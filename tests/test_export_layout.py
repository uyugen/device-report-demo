from lxml import etree
import pytest
from app.export import feature_table, W, NS


@pytest.mark.parametrize('page_width', [9638, 8640])
def test_fixed_feature_table_has_consistent_word_geometry(page_width):
    # Missing grid/cell widths collapses this fixed-layout table in Microsoft Word.
    properties=etree.fromstring(f'<w:tblPr xmlns:w="{W}"><w:tblW w:w="0" w:type="auto"/><w:tblLayout w:type="fixed"/></w:tblPr>')
    rows=[['当前特征及单位','上传值','波形复算值'],['速度有效值 mm/s','2.217','2.217'],['峭度 无量纲','59.101','未提供']]
    table=feature_table(rows,page_width,properties)
    total=table.find('w:tblPr/w:tblW',NS)
    assert total.get('{'+W+'}type')=='dxa'
    assert int(total.get('{'+W+'}w'))==page_width
    grid=[int(c.get('{'+W+'}w')) for c in table.findall('w:tblGrid/w:gridCol',NS)]
    assert len(grid)==3 and sum(grid)==page_width
    assert min(grid)>2000 and grid[0]>grid[1]==grid[2]
    for row,expected in zip(table.findall('w:tr',NS),rows):
        widths=[int(c.get('{'+W+'}w')) for c in row.findall('w:tc/w:tcPr/w:tcW',NS)]
        assert widths==grid
        assert row.xpath('.//w:t/text()',namespaces=NS)==expected
    assert table.find('w:tr/w:trPr/w:tblHeader',NS) is not None
    assert properties.find('w:tblW',NS).get('{'+W+'}type')=='auto'
