from calibre.customize import InterfaceActionBase

__license__ = 'BSD'
__copyright__ = '2026'
__docformat__ = 'restructuredtext en'


class OPDSClientPlugin(InterfaceActionBase):
    name                = 'OPDS Client'
    description         = 'OPDS 서버에서 책을 검색하고 다운로드합니다.'
    supported_platforms = ['windows', 'osx', 'linux']
    author              = 'User'
    version             = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)

    #: 실제 GUI 액션 클래스 (module:ClassName)
    actual_plugin = 'calibre_plugins.opds_client.main:OPDSClientAction'

    def is_customizable(self):
        return False
