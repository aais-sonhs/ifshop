"""Content for the product introduction and customer usage guide."""

DOCUMENT_NAV = [
    {'key': 'retail', 'label': 'Bán lẻ', 'icon': 'fas fa-store'},
    {'key': 'fnb', 'label': 'F&B / Cafe', 'icon': 'fas fa-mug-hot'},
    {'key': 'spa', 'label': 'Spa / Dịch vụ', 'icon': 'fas fa-spa'},
    {'key': 'fashion', 'label': 'Thời trang', 'icon': 'fas fa-tshirt'},
    {'key': 'pharmacy', 'label': 'Nhà thuốc', 'icon': 'fas fa-prescription-bottle-alt'},
    {'key': 'custom', 'label': 'Tùy chỉnh', 'icon': 'fas fa-sliders-h'},
]

FIELD_ALIASES = {
    'restaurant': 'fnb',
    'cafe': 'fnb',
}

DEMO_ACCOUNT = {
    'site': 'Trang quản trị Digimart',
    'username': 'admin_digimart',
    'password': 'abcd@1234',
}

COMMON_MODULES = [
    {
        'icon': 'fas fa-tachometer-alt',
        'title': 'Dashboard điều hành',
        'body': 'Theo dõi doanh thu, đơn hàng, công nợ, khách hàng mới, sản phẩm bán chạy và cảnh báo tồn kho ngay trên màn hình đầu tiên.',
    },
    {
        'icon': 'fas fa-shopping-cart',
        'title': 'Bán hàng, báo giá, đơn hàng',
        'body': 'Tạo báo giá, chuyển thành đơn bán, ghi nhận phí giao hàng, giảm giá, ghi chú, trạng thái đóng gói và in chứng từ.',
    },
    {
        'icon': 'fas fa-tags',
        'title': 'Sản phẩm và kho',
        'body': 'Quản lý danh mục, biến thể, đơn vị tính, giá bán, giá nhập, giá vốn, nhập hàng, kiểm hàng và chuyển kho.',
    },
    {
        'icon': 'fas fa-users',
        'title': 'Khách hàng',
        'body': 'Lưu hồ sơ khách, nhóm khách, thông tin liên hệ, lịch sử mua hàng và dữ liệu chăm sóc sau bán.',
    },
    {
        'icon': 'fas fa-hand-holding-usd',
        'title': 'Thu chi và công nợ',
        'body': 'Lập phiếu thu, phiếu chi, theo dõi đã thu, còn nợ, sổ quỹ và phương thức thanh toán theo từng cửa hàng.',
    },
    {
        'icon': 'fas fa-chart-line',
        'title': 'Báo cáo quản trị',
        'body': 'Báo cáo bán hàng, nhập hàng, tồn kho, tài chính, khách hàng và nhân viên bán hàng giúp chủ shop ra quyết định nhanh.',
    },
]

COMMON_SETUP_STEPS = [
    {
        'title': 'Khai báo thương hiệu và cửa hàng',
        'body': 'Tạo thương hiệu, cửa hàng, kho chính, thông tin liên hệ và mô hình kinh doanh phù hợp với lĩnh vực triển khai.',
    },
    {
        'title': 'Thiết lập người dùng và phân quyền',
        'body': 'Tạo tài khoản cho chủ cửa hàng, quản lý, nhân viên bán hàng, kho, kế toán; giới hạn dữ liệu theo cửa hàng hoặc vai trò.',
    },
    {
        'title': 'Nhập danh mục ban đầu',
        'body': 'Chuẩn hóa sản phẩm, dịch vụ, nhóm khách hàng, nhà cung cấp, phương thức thanh toán và tồn kho đầu kỳ.',
    },
    {
        'title': 'Chạy thử quy trình bán hàng',
        'body': 'Tạo đơn mẫu, in chứng từ, ghi nhận thanh toán, kiểm tra tồn kho và đối chiếu báo cáo trước khi vận hành thật.',
    },
]

COMMON_DAILY_FLOW = [
    {
        'time': 'Đầu ngày',
        'title': 'Kiểm tra dashboard và tồn kho',
        'body': 'Quản lý xem doanh thu hôm trước, đơn cần xử lý, sản phẩm tồn thấp và các khoản thu chi cần theo dõi.',
    },
    {
        'time': 'Trong ngày',
        'title': 'Bán hàng và cập nhật dữ liệu',
        'body': 'Nhân viên tạo đơn, chọn khách, chọn sản phẩm hoặc dịch vụ, ghi nhận thanh toán và in hóa đơn nếu cần.',
    },
    {
        'time': 'Cuối ngày',
        'title': 'Đối soát tiền và báo cáo',
        'body': 'Kế toán hoặc quản lý kiểm tra sổ quỹ, đơn chưa thanh toán, doanh thu theo nhân viên và tồn kho biến động.',
    },
]

COMMON_WORKFLOW_SECTIONS = [
    {
        'title': 'Quản lý sản phẩm, dịch vụ và giá',
        'items': [
            'Tạo danh mục để nhóm sản phẩm theo ngành hàng hoặc nhóm dịch vụ.',
            'Khai báo mã sản phẩm, tên, đơn vị tính, quy cách, vị trí lưu kho, ảnh và giá bán.',
            'Theo dõi giá nhập gần nhất, giá vốn tồn hiện tại và lịch sử nhập để kiểm soát biên lợi nhuận.',
            'Dùng biến thể cho sản phẩm có màu, size, dung tích hoặc nhiều phiên bản bán.',
        ],
    },
    {
        'title': 'Quản lý bán hàng và chứng từ',
        'items': [
            'Lập báo giá cho khách trước khi chốt đơn, sau đó chuyển sang đơn bán khi khách đồng ý.',
            'Tạo đơn trực tiếp từ màn hình bán hàng, thêm sản phẩm, giảm giá, phí giao hàng và ghi chú nội bộ.',
            'Theo dõi trạng thái đơn, đóng gói, trả hàng, duyệt đơn nếu doanh nghiệp bật quy trình phê duyệt.',
            'In hóa đơn A4, phiếu xuất, phiếu bảo hành hoặc hóa đơn khổ K80 tùy cách vận hành.',
        ],
    },
    {
        'title': 'Quản lý kho và nhập hàng',
        'items': [
            'Lập đơn đặt hàng nhập từ nhà cung cấp để dự kiến hàng về.',
            'Tạo phiếu nhập khi nhận hàng, cập nhật tồn kho và giá nhập thực tế.',
            'Kiểm kê định kỳ để phát hiện chênh lệch tồn, thất thoát hoặc sai lệch nhập xuất.',
            'Chuyển kho khi có nhiều cửa hàng hoặc nhiều điểm lưu hàng.',
        ],
    },
    {
        'title': 'Quản lý khách hàng và chăm sóc',
        'items': [
            'Lưu hồ sơ cá nhân hoặc công ty, số điện thoại, địa chỉ, ngày sinh, giới tính và nhóm khách.',
            'Tra cứu lịch sử mua hàng để tư vấn lại, bảo hành, đổi trả hoặc chăm sóc khách thân thiết.',
            'Phân nhóm khách theo hạng, nguồn, khu vực hoặc chính sách giá.',
        ],
    },
    {
        'title': 'Thu chi, công nợ và báo cáo',
        'items': [
            'Ghi nhận phiếu thu theo đơn hàng, phiếu chi cho nhập hàng hoặc chi phí vận hành.',
            'Theo dõi công nợ còn lại của khách và tình trạng thanh toán theo từng đơn.',
            'Xem báo cáo bán hàng, nhập hàng, tồn kho, tài chính và khách hàng để kiểm soát hiệu quả kinh doanh.',
        ],
    },
]

PRODUCT_DOCUMENTS = {
    'retail': {
        'name': 'Digimart cho Bán lẻ / Siêu thị',
        'tagline': 'Một nền tảng gọn, đủ và dễ triển khai để cửa hàng bán nhanh hơn, kiểm kho sát hơn, quản trị rõ hơn.',
        'audience': 'Cửa hàng tạp hóa, siêu thị mini, chuỗi bán lẻ, cửa hàng điện máy, mỹ phẩm, phụ kiện và mô hình phân phối có kho.',
        'business_value': [
            'Tập trung dữ liệu bán hàng, kho, khách hàng và thu chi trên một hệ thống.',
            'Giảm sai lệch tồn kho nhờ nhập hàng, bán hàng, kiểm hàng và chuyển kho được liên kết.',
            'Giúp chủ cửa hàng nhìn thấy doanh thu, lợi nhuận ước tính, công nợ và sản phẩm bán chạy theo thời gian gần thực.',
            'Hỗ trợ mở rộng nhiều cửa hàng mà vẫn quản lý người dùng, kho và báo cáo theo phạm vi.',
        ],
        'positioning': [
            {'title': 'Bán nhanh tại quầy', 'body': 'Màn hình POS và đơn hàng giúp nhân viên thao tác ít bước, chọn khách, chọn sản phẩm và thanh toán nhanh.'},
            {'title': 'Quản kho theo thực tế', 'body': 'Mỗi lần nhập, bán, trả hàng, kiểm kê hoặc chuyển kho đều để lại dữ liệu giúp quản lý đối soát.'},
            {'title': 'Báo cáo cho chủ shop', 'body': 'Chủ cửa hàng xem tình hình kinh doanh thay vì chờ tổng hợp thủ công cuối ngày hoặc cuối tháng.'},
        ],
        'field_workflows': [
            {'title': 'Quy trình bán lẻ chuẩn', 'body': 'Nhân viên mở POS, quét hoặc tìm sản phẩm, chọn khách nếu có, ghi nhận thanh toán, in hóa đơn và hệ thống tự trừ kho.'},
            {'title': 'Nhập hàng và kiểm soát giá vốn', 'body': 'Bộ phận kho tạo phiếu nhập theo nhà cung cấp. Giá nhập mới cập nhật vào lịch sử để quản lý so sánh giá vốn và giá bán.'},
            {'title': 'Kiểm kê theo ca hoặc theo kỳ', 'body': 'Quản lý kiểm hàng các nhóm sản phẩm có rủi ro lệch tồn, ghi nhận số thực tế và theo dõi chênh lệch.'},
            {'title': 'Theo dõi công nợ bán lẻ', 'body': 'Các đơn chưa thu đủ được đưa về thu chi và báo cáo tài chính, giúp kế toán nhắc thu đúng thời điểm.'},
        ],
        'metrics': ['Doanh thu theo ngày/tháng', 'Top sản phẩm bán chạy', 'Tồn kho thấp', 'Công nợ phải thu', 'Lợi nhuận ước tính', 'Hiệu quả nhân viên bán hàng'],
    },
    'fnb': {
        'name': 'Digimart cho Nhà hàng / Quán cafe',
        'tagline': 'Quản lý gọi món, sơ đồ bàn, bán nhanh, thu chi và nguyên vật liệu trong cùng một hệ thống.',
        'audience': 'Quán cafe, trà sữa, nhà hàng nhỏ, mô hình takeaway, quầy đồ uống, bếp trung tâm và chuỗi F&B nhiều điểm bán.',
        'business_value': [
            'Cho phép bật POS bán nhanh và sơ đồ bàn để nhân viên phục vụ xử lý đơn tại quán mượt hơn.',
            'Theo dõi doanh thu theo ca, theo nhân viên, theo bàn hoặc nhóm sản phẩm bán chạy.',
            'Quản lý nguyên vật liệu, hàng hóa, combo và nhập kho để giảm thất thoát.',
            'Tách rõ phiếu thu, phiếu chi, sổ quỹ và báo cáo để chủ quán kiểm soát dòng tiền.',
        ],
        'positioning': [
            {'title': 'Tối ưu vận hành tại quán', 'body': 'Sơ đồ bàn, POS và hóa đơn K80 phù hợp nhịp phục vụ nhanh của cafe, nhà hàng và takeaway.'},
            {'title': 'Kiểm soát thất thoát', 'body': 'Dữ liệu nhập hàng, tồn kho, bán hàng và trả hàng giúp quản lý theo dõi nguyên liệu, đồ uống đóng chai hoặc hàng bán kèm.'},
            {'title': 'Báo cáo theo ca', 'body': 'Quản lý xem doanh thu, sổ quỹ và chi phí phát sinh mỗi ngày để đóng ca minh bạch.'},
        ],
        'field_workflows': [
            {'title': 'Bán tại bàn', 'body': 'Nhân viên chọn bàn, thêm món, cập nhật số lượng, ghi chú yêu cầu của khách, thanh toán và in hóa đơn khi khách rời bàn.'},
            {'title': 'Bán mang đi', 'body': 'Dùng POS để tạo đơn nhanh, chọn phương thức thanh toán, in hóa đơn K80 và ghi nhận doanh thu ngay.'},
            {'title': 'Quản lý nguyên vật liệu', 'body': 'Nhập hàng theo nhà cung cấp, theo dõi tồn kho các mặt hàng quan trọng như cà phê, sữa, topping, bao bì hoặc đồ uống đóng chai.'},
            {'title': 'Đối soát cuối ca', 'body': 'Quản lý kiểm tra đơn đã thanh toán, phiếu thu chi trong ca, tiền mặt thực tế và doanh thu theo phương thức thanh toán.'},
        ],
        'metrics': ['Doanh thu theo ca', 'Bàn đang phục vụ', 'Món bán chạy', 'Chi phí nguyên liệu', 'Tiền mặt cuối ngày', 'Doanh thu theo nhân viên'],
    },
    'spa': {
        'name': 'Digimart cho Spa / Dịch vụ',
        'tagline': 'Tổ chức lịch hẹn, dịch vụ, nhân viên kỹ thuật, phòng và doanh thu dịch vụ trên một phần mềm dễ vận hành.',
        'audience': 'Spa, massage, salon, clinic dịch vụ, chăm sóc da, nail, thẩm mỹ viện nhỏ và chuỗi dịch vụ đặt lịch.',
        'business_value': [
            'Quản lý lịch hẹn dạng lịch và dạng danh sách để lễ tân nắm lịch phục vụ trong ngày.',
            'Khai báo dịch vụ, giá dịch vụ, nhân viên kỹ thuật, phòng và trạng thái đặt lịch.',
            'Gắn khách hàng với lịch sử sử dụng dịch vụ để chăm sóc, đặt lại lịch và tư vấn gói phù hợp.',
            'Theo dõi doanh thu dịch vụ, công nợ, phiếu thu chi và hoa hồng nếu doanh nghiệp bật chính sách nhân viên.',
        ],
        'positioning': [
            {'title': 'Lịch hẹn rõ ràng', 'body': 'Lễ tân xem lịch theo ngày, hạn chế trùng giờ, thiếu phòng hoặc thiếu kỹ thuật viên.'},
            {'title': 'Dịch vụ có cấu trúc', 'body': 'Dịch vụ, giá, nhân viên, phòng và khách hàng được quản lý thống nhất thay vì ghi chép rời rạc.'},
            {'title': 'Chăm sóc khách quay lại', 'body': 'Hồ sơ khách và lịch sử giao dịch giúp đội ngũ tư vấn đúng nhu cầu sau mỗi lần sử dụng dịch vụ.'},
        ],
        'field_workflows': [
            {'title': 'Tiếp nhận và đặt lịch', 'body': 'Lễ tân tạo khách hàng, chọn dịch vụ, thời gian, nhân viên phụ trách, phòng và ghi chú nhu cầu của khách.'},
            {'title': 'Phục vụ tại spa', 'body': 'Nhân viên theo dõi lịch trong ngày, cập nhật trạng thái lịch hẹn và ghi nhận các dịch vụ phát sinh nếu có.'},
            {'title': 'Thanh toán dịch vụ', 'body': 'Sau khi hoàn tất, lễ tân tạo đơn hoặc phiếu thu, chọn phương thức thanh toán và in hóa đơn cho khách.'},
            {'title': 'Chăm sóc sau dịch vụ', 'body': 'Quản lý lọc khách theo lịch sử sử dụng để nhắc lịch, tư vấn gói liệu trình hoặc chương trình ưu đãi.'},
        ],
        'metrics': ['Lịch hẹn trong ngày', 'Doanh thu dịch vụ', 'Khách quay lại', 'Hiệu suất kỹ thuật viên', 'Phòng đang sử dụng', 'Công nợ dịch vụ'],
    },
    'fashion': {
        'name': 'Digimart cho Thời trang / Giày dép',
        'tagline': 'Quản lý sản phẩm nhiều size, màu, mùa vụ, tồn kho và bán hàng đa cửa hàng cho ngành thời trang.',
        'audience': 'Shop quần áo, giày dép, phụ kiện, showroom thời trang, cửa hàng online kết hợp offline và chuỗi bán lẻ.',
        'business_value': [
            'Dùng biến thể để quản lý size, màu, mẫu, chất liệu và nhiều phiên bản bán của cùng một sản phẩm.',
            'Theo dõi tồn kho theo cửa hàng, hỗ trợ chuyển hàng giữa các điểm bán khi lệch size hoặc lệch nhu cầu.',
            'Quản lý giá bán, giá nhập, giá vốn, giảm giá và trả hàng phù hợp đặc thù đổi size, đổi mẫu.',
            'Báo cáo sản phẩm bán chạy và tồn chậm giúp chủ shop ra quyết định nhập hàng, xả hàng hoặc điều chuyển.',
        ],
        'positioning': [
            {'title': 'Biến thể là trọng tâm', 'body': 'Một mẫu áo hoặc giày có thể tách size, màu để bán và kiểm kho chính xác.'},
            {'title': 'Điều chuyển linh hoạt', 'body': 'Khi cửa hàng này thiếu size còn cửa hàng khác dư tồn, phiếu chuyển kho giúp dữ liệu rõ ràng.'},
            {'title': 'Kiểm soát đổi trả', 'body': 'Quy trình trả hàng giúp theo dõi sản phẩm quay lại kho và số tiền cần hoàn hoặc cấn trừ.'},
        ],
        'field_workflows': [
            {'title': 'Tạo sản phẩm theo mẫu và biến thể', 'body': 'Quản lý tạo một sản phẩm cha, sau đó khai báo size, màu, mã biến thể và tồn kho từng biến thể.'},
            {'title': 'Bán hàng tại shop', 'body': 'Nhân viên chọn đúng size, màu, áp dụng giảm giá nếu có, ghi nhận khách hàng và thanh toán.'},
            {'title': 'Đổi trả theo chính sách', 'body': 'Khi khách đổi size hoặc trả hàng, hệ thống ghi nhận đơn trả, cập nhật lại tồn và giữ lịch sử giao dịch.'},
            {'title': 'Điều chuyển mùa vụ', 'body': 'Quản lý xem tồn chậm, tồn thiếu để chuyển hàng giữa kho tổng và cửa hàng trước mỗi chiến dịch bán.'},
        ],
        'metrics': ['Tồn theo size/màu', 'Mẫu bán chạy', 'Tồn chậm', 'Tỷ lệ trả hàng', 'Doanh thu theo cửa hàng', 'Giá vốn theo lô nhập'],
    },
    'pharmacy': {
        'name': 'Digimart cho Nhà thuốc',
        'tagline': 'Quản lý thuốc, vật tư, khách hàng, tồn kho và thu chi với quy trình rõ ràng cho cửa hàng dược.',
        'audience': 'Nhà thuốc, quầy thuốc, cửa hàng vật tư y tế, thực phẩm chức năng và mô hình bán hàng có yêu cầu kiểm tồn chặt.',
        'business_value': [
            'Quản lý danh mục thuốc, đơn vị tính, quy cách, vị trí lưu trữ và giá bán rõ ràng.',
            'Theo dõi nhập hàng, nhà cung cấp, tồn kho thấp và kiểm kê định kỳ để giảm thiếu hàng hoặc sai lệch tồn.',
            'Lưu khách hàng và lịch sử mua để hỗ trợ chăm sóc, nhắc mua lại hoặc đối chiếu giao dịch.',
            'Báo cáo doanh thu, tồn kho và tài chính giúp chủ nhà thuốc kiểm soát hiệu quả vận hành.',
        ],
        'positioning': [
            {'title': 'Tồn kho chính xác', 'body': 'Nhập hàng, bán hàng và kiểm kê được liên kết để hạn chế sai lệch số lượng.'},
            {'title': 'Tra cứu nhanh tại quầy', 'body': 'Nhân viên tìm sản phẩm theo tên, mã, danh mục hoặc vị trí để phục vụ khách nhanh hơn.'},
            {'title': 'Báo cáo dễ theo dõi', 'body': 'Chủ nhà thuốc xem doanh thu, nhóm hàng bán chạy và hàng cần nhập thêm trên báo cáo.'},
        ],
        'field_workflows': [
            {'title': 'Khai báo thuốc và quy cách', 'body': 'Tạo sản phẩm theo nhóm thuốc, đơn vị tính, quy cách đóng gói, vị trí kệ và giá bán.'},
            {'title': 'Bán hàng tại quầy', 'body': 'Nhân viên chọn đúng sản phẩm, kiểm tồn, ghi nhận khách nếu cần và in hóa đơn.'},
            {'title': 'Nhập hàng từ nhà cung cấp', 'body': 'Tạo phiếu nhập theo nhà cung cấp, cập nhật giá nhập và tồn thực tế khi hàng về.'},
            {'title': 'Kiểm kê định kỳ', 'body': 'Quản lý kiểm những nhóm hàng quan trọng để phát hiện thiếu hụt và điều chỉnh kịp thời.'},
        ],
        'metrics': ['Tồn kho thấp', 'Nhóm hàng bán chạy', 'Doanh thu theo ngày', 'Giá nhập gần nhất', 'Công nợ nhà cung cấp', 'Khách mua lại'],
    },
    'custom': {
        'name': 'Digimart cho Mô hình tùy chỉnh',
        'tagline': 'Một khung quản trị linh hoạt để triển khai cho nhiều ngành nghề, bật tắt module theo cách vận hành thực tế.',
        'audience': 'Doanh nghiệp phân phối, showroom, cửa hàng dịch vụ, bán buôn, bán lẻ kết hợp và các mô hình cần cấu hình riêng.',
        'business_value': [
            'Bật tắt module theo mô hình: bán hàng, báo giá, trả hàng, kho, khách hàng, thu chi, báo cáo, POS, spa hoặc bàn cafe.',
            'Mỗi thương hiệu có cấu hình riêng, phù hợp việc triển khai phần mềm cho nhiều lĩnh vực khác nhau.',
            'Dễ mở rộng nhiều cửa hàng, phân quyền người dùng và giới hạn dữ liệu theo phạm vi vận hành.',
            'Giữ quy trình cốt lõi thống nhất trong khi vẫn có phần tài liệu riêng cho từng ngành.',
        ],
        'positioning': [
            {'title': 'Một nền tảng, nhiều ngành', 'body': 'Hệ thống dùng chung nền quản trị nhưng tài liệu, module và thuật ngữ có thể điều chỉnh theo lĩnh vực.'},
            {'title': 'Triển khai theo nhu cầu', 'body': 'Doanh nghiệp chỉ bật những module cần dùng để giao diện gọn và dễ huấn luyện nhân viên.'},
            {'title': 'Dữ liệu tập trung', 'body': 'Dù ngành nào, bán hàng, kho, khách hàng, thu chi và báo cáo vẫn nằm trên cùng một nguồn dữ liệu.'},
        ],
        'field_workflows': [
            {'title': 'Khảo sát nghiệp vụ', 'body': 'Trước triển khai, xác định doanh nghiệp cần bán hàng, báo giá, kho, dịch vụ, lịch hẹn, bàn cafe hay POS nhanh.'},
            {'title': 'Cấu hình module', 'body': 'Chủ thương hiệu vào Mô hình kinh doanh để bật tắt module, tùy chọn hóa đơn, duyệt đơn và tồn âm nếu phù hợp.'},
            {'title': 'Chuẩn hóa dữ liệu', 'body': 'Đội triển khai nhập danh mục sản phẩm, dịch vụ, khách hàng, kho, nhà cung cấp và tài khoản người dùng.'},
            {'title': 'Huấn luyện theo vai trò', 'body': 'Nhân viên bán hàng, kho, kế toán và quản lý được hướng dẫn theo đúng màn hình họ sử dụng hàng ngày.'},
        ],
        'metrics': ['Module đang bật', 'Hiệu quả theo cửa hàng', 'Doanh thu', 'Tồn kho', 'Công nợ', 'Dữ liệu khách hàng'],
    },
}


def normalize_document_key(key):
    """Return a supported documentation key."""
    if not key:
        return ''
    key = FIELD_ALIASES.get(key, key)
    if key in PRODUCT_DOCUMENTS:
        return key
    return ''


def get_product_document(key):
    """Return documentation content and a normalized key."""
    normalized_key = normalize_document_key(key) or 'custom'
    return normalized_key, PRODUCT_DOCUMENTS[normalized_key]
