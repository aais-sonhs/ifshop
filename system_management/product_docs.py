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
    'note': 'Tài khoản đăng nhập demo được cấp riêng trong buổi giới thiệu hoặc bàn giao.',
}

DOCUMENT_REVISION = {
    'date': '17/07/2026',
    'title': 'Cập nhật nghiệp vụ ngày 17/07/2026',
    'summary': (
        'Tài liệu đã được đối chiếu với toàn bộ thay đổi trong ngày: khách hàng và đơn hàng, '
        'tìm sản phẩm khi nhập hàng, bảo mật giá nhập/giá vốn, quản lý kho, báo cáo tồn kho '
        'và cơ chế sinh mã chứng từ an toàn.'
    ),
}

DOCUMENT_UPDATES = [
    {
        'icon': 'fas fa-map-marked-alt',
        'title': 'Khách hàng và địa chỉ giao hàng',
        'items': [
            'Mỗi khách hàng có thể lưu địa chỉ mặc định và nhiều điểm nhận phụ như kho, chi nhánh hoặc địa chỉ công trình.',
            'Mỗi điểm nhận phụ có SĐT nhận hàng riêng; khi chọn điểm nhận trên đơn, hệ thống tự điền đúng SĐT của địa chỉ đó.',
            'Địa chỉ và SĐT nhận hàng được lưu riêng trên từng đơn để giữ đúng lịch sử giao nhận khi hồ sơ khách thay đổi.',
            'Cùng một địa chỉ nhưng khác SĐT người nhận được coi là hai điểm giao riêng, phù hợp trường hợp nhờ người khác nhận hộ.',
            'Khi lưu đơn với một cặp địa chỉ và SĐT chưa có, hệ thống tự thêm điểm nhận này vào hồ sơ khách để dùng lại ngay; điểm nhận cũ vẫn được giữ nguyên.',
            'Khi tạo đơn, có thể chọn địa chỉ trong hồ sơ hoặc dùng lại các địa chỉ giao từng xuất hiện trên đơn trước của đúng khách hàng.',
            'Ở cả tạo mới và sửa đơn, luôn có lựa chọn Nhập địa chỉ khác; lựa chọn này dùng được cả khi khách chưa lưu địa chỉ hoặc đơn khách lẻ.',
            'Khi sửa khách hàng, phần Địa chỉ giao hàng đã dùng hiển thị các địa chỉ lấy từ lịch sử đơn, gộp địa chỉ trùng và cho biết đơn sử dụng gần nhất.',
            'Danh sách khách hàng hiển thị tên ở dòng đầu và mã khách hàng ở dòng dưới trong cùng một cột để bảng gọn hơn.',
            'Danh sách đơn luôn hiển thị thống nhất “Khách lẻ / khách vãng lai” cho đơn không gắn khách hoặc hồ sơ khách cũ bị trống tên.',
            'Tên khách hàng đã lưu trên danh sách đơn là liên kết; bấm vào sẽ mở trang chỉnh sửa khách đó trong tab mới. Khách lẻ không có hồ sơ sẽ không tạo liên kết.',
        ],
    },
    {
        'icon': 'fas fa-file-invoice-dollar',
        'title': 'Báo giá, đơn hàng và chiết khấu',
        'items': [
            'Chiết khấu từng dòng và toàn đơn hỗ trợ nhập theo phần trăm hoặc số tiền; hệ thống tự quy đổi để tính thành tiền.',
            'Có thể sao chép đơn cũ thành đơn nháp mới, sắp xếp dòng hàng theo STT và nhập ngày thanh toán trong quá khứ.',
            'Trường NV bán hàng nằm cùng hàng với địa chỉ giao; có thể tìm theo mã hoặc tên và chọn lại NV đã từng lưu trong đơn cũ.',
            'Form có hai ô sản phẩm: ô ngay dưới Thanh toán lọc mã/tên sản phẩm đã có trong đơn, còn ô tại Chi tiết sản phẩm dùng để tìm và thêm dòng mới. Khi sửa đơn, con trỏ tự vào ô lọc dòng đã có; khi tạo mới, con trỏ tự vào ô thêm sản phẩm.',
            'Tùy chọn Hiệu lực báo giá quyết định việc hiển thị trường, cột danh sách và nội dung hiệu lực trên bản in.',
        ],
    },
    {
        'icon': 'fas fa-box-open',
        'title': 'Sản phẩm và nhập Excel',
        'items': [
            'Danh sách sản phẩm tập trung vào thông tin nhận diện, phân loại và giá; tồn kho được quản lý riêng tại Kho & Sản phẩm → Quản lý kho.',
            'Form sản phẩm được mở rộng và bổ sung kỳ hạn, chính sách bảo hành; chỉnh tồn theo từng kho đã được chuyển khỏi form sản phẩm.',
            'Nhập Excel nhận diện các cột Nhãn hiệu, Thương hiệu, NCC hoặc Nhà cung cấp để gắn nhà cung cấp cho sản phẩm; đồng thời hỗ trợ dữ liệu bảo hành.',
        ],
    },
    {
        'icon': 'fas fa-search-plus',
        'title': 'Tìm và thêm sản phẩm nhanh',
        'items': [
            'Khi tạo đơn bán, có thể tìm sản phẩm bằng một phần tên, mã, barcode, quy cách hoặc danh mục; các từ khóa không bắt buộc phải nằm liền nhau.',
            'Tạo đơn đặt hàng nhập và phiếu nhập đều có ô “Chọn sản phẩm để thêm” phía trên bảng chi tiết; chọn xong sản phẩm được thêm thành một dòng ngay bên dưới.',
            'Kết quả chọn sản phẩm trên đơn đặt hàng nhập và phiếu nhập hiển thị mã, tên, tồn kho thực tế và số lượng có thể bán theo kho nhập đang chọn.',
            'Nếu mạng chậm khi mở đơn đặt hàng nhập hoặc phiếu nhập, ô sản phẩm hiển thị trạng thái đang tải, tự thử lại và có nút “Thử lại” mà không cần F5 cả trang.',
            'Dòng sản phẩm đang rê/chọn trên hai chứng từ nhập dùng nền xanh nhạt để mã, tên và các chỉ số tồn kho luôn dễ đọc.',
            'Ô chọn nhanh trên chứng từ nhập chỉ dựng từng nhóm kết quả phù hợp khi tìm kiếm; riêng phiếu nhập hiển thị 5 kết quả mỗi lượt, giúp mở và chọn nhanh ngay cả khi danh mục có nhiều sản phẩm.',
            'Có thể tìm bằng một phần tên, mã, barcode, quy cách hoặc từ khóa không dấu; không bắt buộc gõ đầy đủ và đúng liền mạch toàn bộ tên sản phẩm.',
            'Nếu chọn lại đúng sản phẩm/biến thể đã có trong chứng từ, hệ thống không thêm dòng trùng mà đưa con trỏ về ô số lượng của dòng hiện có.',
            'Giá nhập được điền gợi ý từ dữ liệu sản phẩm và vẫn có thể sửa trực tiếp trên từng dòng trước khi lưu phiếu nhập.',
        ],
    },
    {
        'icon': 'fas fa-user-shield',
        'title': 'Bảo mật giá nhập và giá vốn khi bán hàng',
        'items': [
            'Trong ô tìm/chọn sản phẩm khi tạo đơn bán, Chủ thương hiệu, Giám đốc và Kế toán được xem Giá bán, Giá nhập và Giá vốn.',
            'Các tài khoản khác chỉ thấy Giá bán; Giá nhập và Giá vốn được ẩn ngay trong kết quả tìm kiếm sản phẩm để tránh lộ thông tin nội bộ.',
        ],
    },
    {
        'icon': 'fas fa-warehouse',
        'title': 'Quản lý tồn kho và số lượng có thể bán',
        'items': [
            'Màn hình Quản lý kho hiển thị Tồn kho tối thiểu, Tồn kho tối đa, Tồn kho thực tế và Có thể bán của từng sản phẩm.',
            'Ô tìm kiếm trên bảng tồn kho hỗ trợ tìm theo tên hoặc mã sản phẩm, kể cả khi nhập không dấu.',
            'Có thể bán = Tồn kho thực tế − số lượng đang giữ cho các đơn ở trạng thái Đơn hàng, Đang xử lý hoặc Đang đóng gói và đã đủ điều kiện duyệt.',
            'Có thể sắp xếp Có thể bán hoặc Tồn kho theo thứ tự tăng/giảm; bộ chọn Tồn kho còn hỗ trợ lọc riêng các sản phẩm đang âm kho.',
            'Bấm Sửa tại sản phẩm để điều chỉnh tồn theo từng kho và xem lịch sử nhập; tồn combo chỉ xem vì được tính tự động từ thành phần.',
            'Hai cột Tồn kho tối thiểu và Tồn kho tối đa là ngưỡng riêng của từng sản phẩm. Bấm Sửa để điều chỉnh: mức tối thiểu được phép là số âm; mức tối đa bằng 0 nếu không giới hạn. Đây không phải số lượng của từng kho.',
            'Chỉ được lưu số lượng âm khi thương hiệu đã bật cấu hình Cho phép tồn âm; nếu chưa bật, hệ thống giữ nguyên tồn cũ và báo rõ kho cần cấu hình.',
        ],
    },
    {
        'icon': 'fas fa-exclamation-triangle',
        'title': 'Báo cáo và cảnh báo tồn kho',
        'items': [
            'Tổng giá trị tồn kho = tổng của từng sản phẩm có tồn dương × giá vốn; tồn âm là chênh lệch cần xử lý và không làm giảm giá trị hàng đang còn.',
            'Bộ lọc Danh mục sản phẩm chỉ chứa danh mục gốc; bộ lọc Loại sản phẩm chứa các loại con và tự thu hẹp theo danh mục đã chọn.',
            'BC Kho tách rõ sản phẩm dưới tồn tối thiểu và trên tồn tối đa.',
            'Cột Cần nhập tối thiểu cho biết số lượng cần bổ sung; bấm thẻ Cảnh báo để lọc nhanh các mã cần xử lý.',
            'Khi xuất Excel, bộ lọc Danh mục và Loại sản phẩm tiếp tục được áp dụng giống dữ liệu đang xem.',
        ],
    },
    {
        'icon': 'fas fa-fingerprint',
        'title': 'Sinh mã tự động và xử lý mã trùng',
        'items': [
            'Mã tự động được lấy theo số lớn nhất đã dùng và không tái sử dụng mã của bản ghi đã xóa mềm.',
            'Khi nhiều người lưu đồng thời, hệ thống tự sinh lại mã và thử lưu an toàn thay vì trả lỗi ràng buộc mã trùng.',
            'Áp dụng cho các luồng sinh mã liên quan như khách hàng, nhà cung cấp, sản phẩm, phiếu thu/chi, báo giá, POS, phiếu nhập, trả hàng nhập, kiểm kho, trả hàng bán và lịch hẹn.',
            'Nếu người dùng chủ động nhập một mã đã tồn tại, hệ thống báo rõ mã bị trùng để chọn mã khác.',
        ],
    },
    {
        'icon': 'fas fa-truck-loading',
        'title': 'Báo cáo nhập hàng theo nhà cung cấp',
        'items': [
            'Vào Báo cáo → BC Nhập hàng, chọn tháng hoặc khoảng ngày để xem đã nhập của từng nhà cung cấp bao nhiêu phiếu và bao nhiêu tiền hàng.',
            'Có thể lọc riêng một nhà cung cấp; file Excel có thêm sheet Tổng hợp NCC.',
        ],
    },
    {
        'icon': 'fas fa-shield-alt',
        'title': 'Phiếu bảo hành theo đơn',
        'items': [
            'Sản phẩm lưu sẵn kỳ hạn và chính sách bảo hành để tự động điền khi lập phiếu.',
            'Đơn đã Xuất kho hoặc Hoàn thành có thể Lưu & In phiếu bảo hành, chọn sản phẩm, số lượng, serial/lô và điều chỉnh chính sách trước khi lưu.',
            'Phiếu được liên kết với đơn, giữ bản chụp chính sách tại thời điểm bán và hiển thị nhãn Đã có PBH trong danh sách.',
        ],
    },
    {
        'icon': 'fas fa-desktop',
        'title': 'Giao diện thao tác và mẫu in',
        'items': [
            'Tại Cấu hình → Nhãn hàng, đặt Thứ tự ưu tiên bằng số; số nhỏ đứng trước trong danh sách chọn nhãn hàng ở Cấu hình in chứng từ và khi in.',
            'Form đơn hàng và sản phẩm được mở rộng, các vùng nhập hàng có cuộn độc lập để thao tác tốt hơn với chứng từ dài.',
            'Hóa đơn K80 tách tên hàng khỏi dòng số lượng, đơn giá và thành tiền để dễ đọc hơn.',
            'Cảnh báo bán dưới giá vốn vẫn cho lưu đơn, phù hợp trường hợp hàng tặng hoặc khuyến mãi giá 0.',
        ],
    },
]

COMMON_MODULES = [
    {
        'icon': 'fas fa-tachometer-alt',
        'title': 'Dashboard điều hành',
        'body': 'Màn hình tổng quan hiển thị doanh thu ngày/tháng, đơn hàng mới, đơn chờ xử lý, công nợ phải thu, sản phẩm bán chạy nhất, tồn kho thấp và cảnh báo quan trọng. Chủ cửa hàng có thể xem nhanh tình hình kinh doanh mà không cần mở từng báo cáo.',
    },
    {
        'icon': 'fas fa-shopping-cart',
        'title': 'Bán hàng, báo giá, đơn hàng',
        'body': 'Tạo báo giá cho khách trước khi chốt đơn, chuyển báo giá thành đơn bán khi khách đồng ý. Hỗ trợ chiết khấu theo tiền hoặc %, sao chép đơn, địa chỉ giao hàng, phí phát sinh, phê duyệt, xuất kho và lưu/in phiếu bảo hành.',
    },
    {
        'icon': 'fas fa-tags',
        'title': 'Sản phẩm và kho',
        'body': 'Quản lý danh mục sản phẩm, biến thể, đơn vị tính, giá bán, giá nhập, giá vốn, nhà cung cấp và chính sách bảo hành. Nhập Excel, nhập hàng, kiểm kê, chuyển kho và theo dõi cảnh báo tồn tối thiểu/tối đa.',
    },
    {
        'icon': 'fas fa-users',
        'title': 'Khách hàng',
        'body': 'Lưu hồ sơ khách cá nhân và doanh nghiệp, địa chỉ mặc định, nhiều điểm nhận hàng, nhóm khách, thông tin liên hệ, lịch sử mua, công nợ, điểm thưởng và dữ liệu chăm sóc sau bán.',
    },
    {
        'icon': 'fas fa-hand-holding-usd',
        'title': 'Thu chi và công nợ',
        'body': 'Lập phiếu thu theo đơn hàng, phiếu chi cho nhập hàng hoặc chi phí vận hành. Theo dõi đã thu, còn nợ, sổ quỹ theo ngày, phương thức thanh toán (tiền mặt, chuyển khoản, thẻ, ví điện tử) và đối soát cuối ngày.',
    },
    {
        'icon': 'fas fa-chart-line',
        'title': 'Báo cáo quản trị',
        'body': 'Báo cáo bán hàng theo ngày/tháng/nhân viên, nhập hàng theo nhà cung cấp, cảnh báo tồn kho, tài chính, công nợ và hiệu quả nhân viên. Hỗ trợ lọc theo cửa hàng, kho, thời gian, nhà cung cấp và xuất Excel.',
    },
]

COMMON_SETUP_STEPS = [
    {
        'title': 'Khai báo thương hiệu và cửa hàng',
        'body': 'Tạo thương hiệu (brand), cửa hàng (store), kho chính, thông tin liên hệ, địa chỉ và mô hình kinh doanh phù hợp với lĩnh vực triển khai. Nếu có nhiều cửa hàng, tạo từng cửa hàng và kho tương ứng.',
    },
    {
        'title': 'Thiết lập người dùng và phân quyền',
        'body': 'Tạo tài khoản cho chủ cửa hàng, quản lý, nhân viên bán hàng, kho, kế toán. Gán cửa hàng cho từng người dùng, thiết lập nhóm vai trò (Giám đốc, Kế toán, Quản lý, Nhân viên bán hàng, Nhân viên kho) và giới hạn phạm vi dữ liệu theo cửa hàng hoặc vai trò.',
    },
    {
        'title': 'Nhập danh mục ban đầu',
        'body': 'Chuẩn bị và nhập: sản phẩm/dịch vụ (tên, mã, đơn vị tính, giá bán, giá nhập), nhóm khách hàng, nhà cung cấp, phương thức thanh toán, tồn kho đầu kỳ. Với ngành thời trang cần khai báo biến thể size/màu. Với F&B cần khai báo menu và giá.',
    },
    {
        'title': 'Chạy thử quy trình bán hàng',
        'body': 'Tạo đơn mẫu từ đầu tới cuối: chọn khách, thêm sản phẩm, thanh toán, in hóa đơn. Kiểm tra tồn kho sau bán, đối chiếu báo cáo bán hàng và thu chi. Điều chỉnh cấu hình nếu chưa phù hợp trước khi vận hành thật.',
    },
]

PAYMENT_METHOD_DEFAULT_GUIDE = {
    'title': 'Cấu hình tài khoản/quỹ mặc định cho phương thức thanh toán',
    'intro': (
        'Đây là cấu hình quan trọng trước khi thu tiền, chi tiền hoặc hoàn tiền. '
        'Mỗi phương thức như Tiền mặt, Chuyển khoản hoặc MoMo nên được gắn đúng quỹ '
        'để hệ thống tự ghi nhận phiếu thu/chi và số dư sổ quỹ.'
    ),
    'steps': [
        {
            'title': '1. Tạo quỹ hoặc tài khoản',
            'body': 'Vào Tài chính → Sổ quỹ và bấm Tạo quỹ ở góc phải. Nếu phiên bản giao diện chưa có nút này, vào Quản trị → Danh mục → Danh mục quỹ → Thêm. Tạo Quỹ tiền mặt, Tài khoản ngân hàng, Ví MoMo hoặc tài khoản thực tế cửa hàng đang sử dụng.',
        },
        {
            'title': '2. Mở phương thức thanh toán',
            'body': 'Vào Cài đặt → Phương thức TT. Tìm phương thức cần cấu hình, ví dụ Tiền mặt, Chuyển khoản hoặc MoMo, rồi bấm Sửa.',
        },
        {
            'title': '3. Chọn tài khoản mặc định',
            'body': 'Tại trường Tài khoản mặc định, chọn đúng quỹ tương ứng với phương thức. Ví dụ Tiền mặt gắn Quỹ tiền mặt; Chuyển khoản gắn Tài khoản ngân hàng.',
        },
        {
            'title': '4. Lưu và kiểm tra',
            'body': 'Bấm Lưu. Mở thử một đơn hoặc phiếu hoàn tiền, chọn phương thức vừa cấu hình và kiểm tra hệ thống đã tự chọn đúng tài khoản/quỹ.',
        },
        {
            'title': '5. Đặt phương thức ưu tiên',
            'body': 'Tại trường Số thứ tự, nhập số nhỏ hơn cho phương thức muốn hiển thị đầu tiên (ví dụ 1 cho Tiền mặt, 2 cho Chuyển khoản). Khi mở phiếu hoàn, hệ thống chọn sẵn phương thức đang hoạt động có số thứ tự ưu tiên nhất; người thao tác vẫn có thể đổi sang phương thức khác.',
        },
    ],
    'checks': [
        'Không gắn nhiều phương thức khác bản chất vào cùng một quỹ nếu kế toán cần đối soát riêng.',
        'Quỹ được chọn phải đang hoạt động và đúng với tài khoản thực tế nhận hoặc chi tiền.',
        'Khi hoàn hàng, nếu phương thức đã có quỹ mặc định thì hệ thống tự chọn quỹ đó.',
        'Nếu phương thức chưa có quỹ mặc định, người dùng phải chọn Tài khoản/quỹ hoàn tiền trực tiếp trên phiếu.',
    ],
    'error': (
        'Nếu gặp thông báo “Phương thức hoàn tiền chưa có tài khoản/quỹ mặc định để ghi nhận phiếu chi”, '
        'hãy quay lại Cài đặt → Phương thức TT để gắn quỹ hoặc chọn quỹ trực tiếp trên phiếu hoàn.'
    ),
}

COMMON_DAILY_FLOW = [
    {
        'time': 'Đầu ngày',
        'title': 'Kiểm tra dashboard và tồn kho',
        'body': 'Quản lý mở dashboard để xem doanh thu hôm trước, đơn cần xử lý hôm nay, sản phẩm tồn thấp cần nhập补充, các khoản thu chi chưa đối soát và cảnh báo quan trọng.',
    },
    {
        'time': 'Trong ngày',
        'title': 'Bán hàng và cập nhật dữ liệu',
        'body': 'Nhân viên tạo đơn từ POS hoặc màn hình bán hàng, chọn khách, thêm sản phẩm/dịch vụ, kiểm tra tồn, ghi nhận thanh toán và in hóa đơn. Quản lý theo dõi đơn lớn, đơn cần duyệt và xử lý trả hàng nếu có.',
    },
    {
        'time': 'Cuối ngày',
        'title': 'Đối soát tiền và báo cáo',
        'body': 'Kế toán hoặc quản lý kiểm tra sổ quỹ, đối chiếu tiền mặt thực tế với phiếu thu, kiểm tra đơn chưa thanh toán, xem doanh thu theo nhân viên, tồn kho biến động và báo cáo tổng kết ngày.',
    },
]

COMMON_WORKFLOW_SECTIONS = [
    {
        'title': 'Quản lý sản phẩm, dịch vụ và giá',
        'items': [
            'Tạo danh mục để nhóm sản phẩm theo ngành hàng hoặc nhóm dịch vụ (ví dụ: Đồ uống, Món chính, Combo).',
            'Khai báo mã sản phẩm, tên, đơn vị tính, quy cách, vị trí lưu kho, ảnh và giá bán theo từng cửa hàng.',
            'Theo dõi giá nhập gần nhất, giá vốn bình quân gia quyền từ lịch sử nhập và biên lợi nhuận.',
            'Giá nhập và giá vốn trong ô tìm sản phẩm khi tạo đơn chỉ hiển thị cho Chủ thương hiệu, Giám đốc và Kế toán; các vai trò khác chỉ thấy giá bán.',
            'Dùng biến thể cho sản phẩm có màu, size, dung tích hoặc nhiều phiên bản bán.',
            'Khai báo kỳ hạn và chính sách bảo hành để dùng tự động khi lập phiếu bảo hành theo đơn.',
            'Khi nhập Excel, có thể dùng cột Nhãn hiệu/Thương hiệu/NCC/Nhà cung cấp để gắn nhà cung cấp cho sản phẩm.',
            'Cập nhật giá bán khi có chương trình khuyến mãi hoặc thay đổi giá theo thị trường.',
        ],
    },
    {
        'title': 'Quản lý bán hàng và chứng từ',
        'items': [
            'Lập báo giá cho khách trước khi chốt đơn, sau đó chuyển sang đơn bán khi khách đồng ý.',
            'Tạo hoặc sao chép đơn từ màn hình bán hàng, thêm sản phẩm, chọn địa chỉ giao, giảm giá theo tiền hoặc %, phí giao hàng và ghi chú.',
            'Tại danh sách đơn, bấm tên khách hàng đã lưu để mở trang chỉnh sửa khách trong tab mới; các đơn khách lẻ luôn có nhãn thống nhất.',
            'Theo dõi trạng thái đơn: chờ xử lý, đã duyệt, đang đóng gói, đã giao, hoàn thành, trả hàng.',
            'Sau khi xuất kho, lưu và in phiếu bảo hành có serial/lô, kỳ hạn, ngày bắt đầu/kết thúc và chính sách tại thời điểm bán.',
            'In hóa đơn A4, phiếu xuất, phiếu bảo hành hoặc hóa đơn khổ K80 tùy cách vận hành.',
            'Nếu doanh nghiệp bật duyệt đơn, nhân viên tạo đơn và quản lý duyệt trước khi giao hàng.',
        ],
    },
    {
        'title': 'Quản lý kho và nhập hàng',
        'items': [
            'Vào Kho & Sản phẩm → Quản lý kho để xem Tồn kho thực tế và số lượng Có thể bán của từng sản phẩm.',
            'Có thể bán được tính bằng Tồn kho trừ số lượng đang giữ cho đơn chưa xuất kho; nếu không có đơn giữ hàng thì hai số bằng nhau.',
            'Bấm Sửa tại từng sản phẩm để chỉnh tồn theo kho và xem lịch sử nhập hàng.',
            'Lập đơn đặt hàng nhập từ nhà cung cấp để dự kiến hàng về.',
            'Ở đơn đặt hàng nhập hoặc phiếu nhập, dùng ô Chọn sản phẩm để thêm; có thể tìm theo một phần tên, mã, barcode hoặc quy cách.',
            'Tạo phiếu nhập khi nhận hàng, điều chỉnh số lượng và giá nhập thực tế trên từng dòng rồi lưu để cập nhật tồn kho.',
            'Kiểm kê định kỳ để phát hiện chênh lệch tồn, thất thoát hoặc sai lệch nhập xuất.',
            'Chuyển kho khi có nhiều cửa hàng hoặc nhiều điểm lưu hàng.',
            'Theo dõi hàng dưới tồn tối thiểu, trên tồn tối đa, tồn âm và số lượng cần nhập bổ sung trên BC Kho.',
        ],
    },
    {
        'title': 'Quản lý khách hàng và chăm sóc',
        'items': [
            'Lưu hồ sơ cá nhân hoặc công ty, số điện thoại, địa chỉ mặc định, nhiều điểm nhận phụ, ngày sinh, giới tính và nhóm khách.',
            'Khi tạo đơn mới, hệ thống gợi ý cả địa chỉ trong hồ sơ và địa chỉ giao đã dùng trên các đơn trước của khách.',
            'Tra cứu lịch sử mua hàng để tư vấn lại, bảo hành, đổi trả hoặc chăm sóc khách thân thiết.',
            'Phân nhóm khách theo hạng (VIP, Thân thiết, Thường), nguồn (Online, Cửa hàng, Giới thiệu) và khu vực.',
            'Theo dõi công nợ của từng khách và nhắc thu đúng thời điểm.',
        ],
    },
    {
        'title': 'Thu chi, công nợ và báo cáo',
        'items': [
            'Ghi nhận phiếu thu theo đơn hàng, phiếu chi cho nhập hàng hoặc chi phí vận hành.',
            'Theo dõi công nợ còn lại của khách và tình trạng thanh toán theo từng đơn.',
            'Xem sổ quỹ theo ngày để kiểm soát dòng tiền vào/ra.',
            'Xem BC Nhập hàng theo tháng để biết nhập của nhà cung cấp nào, số phiếu hoàn thành và tổng tiền hàng của từng nhà cung cấp.',
            'Trên BC Kho, Tổng giá trị tồn chỉ cộng tồn dương × giá vốn; lọc riêng Danh mục sản phẩm và Loại sản phẩm khi cần đối chiếu.',
            'Xem báo cáo bán hàng, cảnh báo tồn kho, tài chính và khách hàng để kiểm soát hiệu quả kinh doanh.',
        ],
    },
]

ROLE_GUIDES = [
    {
        'role': 'Chủ doanh nghiệp / Chủ thương hiệu',
        'goal': 'Nắm tình hình vận hành, kiểm soát dữ liệu, phân quyền người dùng và ra quyết định dựa trên báo cáo.',
        'permissions': [
            'Quản lý thương hiệu, cửa hàng, mô hình kinh doanh và các tùy chọn bật tắt module.',
            'Tạo tài khoản nhân viên, gán cửa hàng, phân quyền theo vai trò và kiểm tra phạm vi dữ liệu.',
            'Xem dashboard, báo cáo bán hàng, báo cáo tồn kho, báo cáo tài chính, công nợ và hiệu quả nhân viên.',
            'Duyệt đơn hàng hoặc quy trình nội bộ nếu doanh nghiệp bật chức năng phê duyệt.',
            'Cấu hình mẫu in, máy in, phương thức thanh toán và các tùy chọn kinh doanh.',
        ],
        'daily_tasks': [
            'Đầu ngày xem dashboard để biết doanh thu, đơn chưa xử lý, công nợ và cảnh báo tồn kho.',
            'Trong ngày theo dõi các đơn lớn, đơn cần duyệt, sản phẩm bán nhanh hoặc tồn thấp.',
            'Cuối ngày đối chiếu doanh thu, sổ quỹ, phiếu thu chi, đơn chưa thanh toán và báo cáo theo nhân viên.',
            'Định kỳ rà soát quyền nhân viên, cửa hàng đang hoạt động và cấu hình module theo mô hình kinh doanh.',
        ],
    },
    {
        'role': 'Quản lý cửa hàng',
        'goal': 'Điều phối bán hàng, kiểm kho, xử lý đơn, theo dõi nhân viên và đảm bảo dữ liệu trong ngày chính xác.',
        'permissions': [
            'Xem dữ liệu trong cửa hàng được phân công.',
            'Tạo, sửa, theo dõi đơn hàng, báo giá, trả hàng, đóng gói và khách hàng.',
            'Kiểm tra tồn kho, tạo đề xuất nhập hàng, kiểm hàng hoặc chuyển kho khi được cấp quyền.',
            'Xem các báo cáo vận hành cần thiết cho cửa hàng.',
            'Duyệt đơn nhỏ hoặc xử lý giảm giá đặc biệt theo thẩm quyền.',
        ],
        'daily_tasks': [
            'Kiểm tra đơn tồn, đơn cần đóng gói, hàng tồn thấp và lịch giao hàng.',
            'Hỗ trợ nhân viên xử lý giảm giá, đổi trả, thanh toán thiếu hoặc khách hàng đặc biệt.',
            'Kiểm tra phiếu thu chi phát sinh trong ca và xác nhận tiền cuối ngày.',
            'Báo lại cho chủ doanh nghiệp các mặt hàng cần nhập, tồn chậm hoặc lỗi dữ liệu cần chỉnh.',
        ],
    },
    {
        'role': 'Nhân viên bán hàng / Lễ tân',
        'goal': 'Tạo giao dịch nhanh, đúng giá, đúng khách, đúng phương thức thanh toán và in chứng từ khi cần.',
        'permissions': [
            'Tạo đơn hàng, báo giá hoặc POS theo quyền được cấp.',
            'Tìm kiếm sản phẩm, dịch vụ, khách hàng và áp dụng giảm giá trong phạm vi cho phép.',
            'Ghi nhận thanh toán, in hóa đơn, phiếu xuất hoặc phiếu dịch vụ.',
            'Tạo khách hàng mới và cập nhật thông tin liên hệ cơ bản.',
        ],
        'daily_tasks': [
            'Mở màn hình bán hàng hoặc POS, kiểm tra đúng cửa hàng/kho trước khi tạo đơn.',
            'Chọn khách hàng, thêm sản phẩm/dịch vụ, kiểm tra giá, số lượng, giảm giá và ghi chú.',
            'Xác nhận phương thức thanh toán, số tiền khách trả, công nợ còn lại và in chứng từ.',
            'Cuối ca rà lại đơn đã tạo, đơn chưa thanh toán và bàn giao cho quản lý nếu có phát sinh.',
        ],
    },
    {
        'role': 'Nhân viên kho',
        'goal': 'Đảm bảo tồn kho đúng thực tế, nhập hàng đúng giá, chuyển hàng đúng điểm và kiểm kê có đối chiếu.',
        'permissions': [
            'Xem danh sách sản phẩm, tồn kho, kho, vị trí lưu trữ và lịch sử nhập.',
            'Tạo đơn đặt hàng nhập, phiếu nhập, phiếu kiểm hàng và phiếu chuyển kho theo quyền.',
            'Cập nhật số lượng thực nhận, giá nhập, nhà cung cấp và ghi chú chênh lệch.',
            'Theo dõi hàng tồn thấp, hàng tồn âm, hàng cần điều chuyển hoặc cần kiểm kê.',
        ],
        'daily_tasks': [
            'Kiểm tra cảnh báo tồn thấp và danh sách hàng cần nhập.',
            'Khi hàng về, đối chiếu đơn đặt hàng nhập với số lượng thực nhận rồi tạo phiếu nhập.',
            'Kiểm tra chênh lệch tồn, ghi rõ lý do kiểm kê và báo quản lý trước khi xác nhận.',
            'Cuối ngày đối chiếu hàng bán, hàng trả, hàng chuyển và tồn thực tế các mặt hàng rủi ro cao.',
        ],
    },
    {
        'role': 'Kế toán / Thu ngân',
        'goal': 'Kiểm soát dòng tiền, công nợ, phiếu thu chi, phương thức thanh toán và đối soát cuối ngày.',
        'permissions': [
            'Tạo phiếu thu, phiếu chi, theo dõi sổ quỹ và danh sách giao dịch tài chính.',
            'Xem đơn hàng liên quan tới thanh toán, công nợ phải thu và khoản đã thu.',
            'Cấu hình phương thức thanh toán nếu được phân quyền quản trị.',
            'Xuất hoặc xem báo cáo tài chính theo ngày, tháng, cửa hàng hoặc phương thức thanh toán.',
        ],
        'daily_tasks': [
            'Kiểm tra số dư đầu ngày và phiếu thu chi chưa đối soát.',
            'Ghi nhận đúng phương thức thanh toán: tiền mặt, chuyển khoản, thẻ hoặc ví điện tử.',
            'Theo dõi các đơn còn nợ, phiếu thu bổ sung và khoản chi phát sinh trong ngày.',
            'Cuối ngày đối chiếu tiền mặt thực tế, chuyển khoản nhận được, sổ quỹ và báo cáo doanh thu.',
        ],
    },
]

DETAILED_OPERATION_GUIDES = [
    {
        'title': 'Tạo khách hàng và dùng lại dữ liệu khách',
        'goal': 'Lưu thông tin khách để tạo đơn nhanh, theo dõi lịch sử mua, công nợ, bảo hành và chăm sóc sau bán.',
        'steps': [
            'Vào menu Khách hàng, chọn DS Khách hàng.',
            'Nhấn nút "Tạo mới" để mở form nhập thông tin khách hàng.',
            'Nhập tên khách, số điện thoại (bắt buộc để tìm nhanh), email, địa chỉ, nhóm khách và thông tin bổ sung.',
            'Nếu khách là doanh nghiệp, nhập thêm tên công ty, mã số thuế, địa chỉ xuất hóa đơn và người liên hệ.',
            'Tại phần Địa chỉ / điểm nhận phụ, thêm tên điểm nhận, địa chỉ và SĐT nhận hàng cho từng kho, chi nhánh hoặc công trình của khách.',
            'Lưu khách hàng. Hệ thống tự động tạo hồ sơ khách để dùng cho các đơn hàng sau.',
            'Khi tạo đơn hàng, tìm khách rồi chọn nhanh địa chỉ trong hồ sơ hoặc địa chỉ giao đã dùng trên đơn trước; hệ thống tự lấy SĐT của điểm nhận, hoặc chọn Nhập địa chỉ khác để nhập địa chỉ và SĐT thủ công.',
            'Tại danh sách đơn hàng, bấm vào tên khách đã lưu để mở thẳng form chỉnh sửa khách trong một tab mới.',
            'Trong form sửa, xem phần Địa chỉ giao hàng đã dùng để tra cứu các điểm từng giao; đây là dữ liệu chỉ đọc từ lịch sử đơn và không thay đổi chứng từ cũ.',
            'Định kỳ phân nhóm khách để chạy chương trình chăm sóc, chính sách giá hoặc báo cáo khách hàng.',
        ],
        'checks': [
            'Không tạo trùng khách nếu số điện thoại đã tồn tại.',
            'Luôn kiểm tra nhóm khách trước khi áp dụng chính sách giá.',
            'Với khách công nợ, cần nhập đúng thông tin liên hệ để nhắc thu sau này.',
            'Kiểm tra đúng điểm nhận trước khi lưu đơn, nhất là khách có nhiều kho hoặc chi nhánh.',
            'Đơn không gắn hồ sơ khách sẽ không có liên kết chỉnh sửa. Nếu đơn còn gắn một hồ sơ cũ bị trống tên, hệ thống hiển thị nhãn “Khách lẻ / khách vãng lai” nhưng vẫn cho mở hồ sơ đó để bổ sung thông tin.',
            'Sau khi tạo khách mới, kiểm tra lại thông tin trước khi dùng cho đơn hàng quan trọng.',
        ],
    },
    {
        'title': 'Xem địa chỉ khách hàng và lịch sử giao hàng',
        'goal': 'Tra cứu đầy đủ nơi nhận hàng của khách để chọn đúng địa chỉ khi tư vấn, tạo đơn hoặc giao lại lần sau.',
        'steps': [
            'Vào Khách hàng → DS Khách hàng, tìm khách bằng tên, mã khách hàng hoặc số điện thoại.',
            'Trong cột Tên khách hàng, dòng đầu là tên và dòng dưới là mã khách hàng để đối chiếu đúng hồ sơ.',
            'Bấm Sửa tại dòng khách hàng cần xem. Nếu đang ở DS Đơn hàng, có thể bấm trực tiếp tên khách để mở form sửa trong tab mới.',
            'Địa chỉ mặc định là địa chỉ được chọn ưu tiên khi tạo đơn mới.',
            'Địa chỉ / điểm nhận phụ là các kho, chi nhánh hoặc công trình đã lưu trực tiếp trong hồ sơ; mỗi dòng có thể lưu SĐT nhận hàng riêng và người dùng có thể thêm, sửa hoặc xóa.',
            'Địa chỉ giao hàng đã dùng được tổng hợp tự động từ các đơn của đúng khách hàng và đúng phạm vi cửa hàng.',
            'Mỗi cặp địa chỉ và SĐT nhận lịch sử chỉ hiển thị một lần; hệ thống cho biết đơn dùng gần nhất, ngày gần nhất và số đơn đã sử dụng điểm giao đó.',
            'Nếu cùng địa chỉ nhưng khác SĐT nhận hàng, hệ thống giữ thành các lựa chọn riêng và không ghi đè người nhận cũ.',
            'Khi tạo đơn tiếp theo, danh sách chọn gồm địa chỉ mặc định, điểm nhận phụ và các địa chỉ giao đã dùng trước đây; chọn một dòng sẽ điền cả địa chỉ và SĐT nhận.',
        ],
        'checks': [
            'Địa chỉ đã trùng với địa chỉ mặc định hoặc điểm nhận phụ sẽ không hiển thị lặp lại trong phần lịch sử giao hàng.',
            'Phần Địa chỉ giao hàng đã dùng chỉ đọc; sửa hồ sơ khách không làm thay đổi địa chỉ hoặc SĐT nhận hàng đã lưu trên chứng từ cũ.',
            'Xóa một điểm nhận phụ khỏi hồ sơ không xóa địa chỉ giao hàng trong lịch sử đơn.',
            'Đơn không gắn hồ sơ khách sẽ hiển thị Khách lẻ / khách vãng lai và không có liên kết mở hồ sơ địa chỉ.',
        ],
    },
    {
        'title': 'Tạo báo giá và chuyển thành đơn hàng',
        'goal': 'Dùng cho khách cần chốt giá trước, gửi báo giá, sau đó chuyển sang đơn bán khi khách đồng ý.',
        'steps': [
            'Vào DS báo giá hoặc màn hình báo giá.',
            'Chọn khách hàng từ danh sách hoặc tạo mới nếu khách chưa có.',
            'Nhập ngày báo giá, thời hạn hiệu lực và người phụ trách nếu doanh nghiệp bật các tùy chọn này.',
            'Thêm sản phẩm hoặc dịch vụ; tại mỗi dòng có thể chọn chiết khấu theo % hoặc số tiền rồi kiểm tra thành tiền.',
            'Ở phần tổng đơn, chọn Số tiền hoặc Phần trăm cho chiết khấu chung; hệ thống hiển thị số tiền quy đổi.',
            'Lưu báo giá. In hoặc gửi cho khách theo quy trình nội bộ (email, Zalo, in giấy).',
            'Khi khách đồng ý, chọn chức năng "Chuyển thành đơn hàng" để tiếp tục thanh toán, xuất kho và in hóa đơn.',
        ],
        'checks': [
            'Nếu cần ẩn hiệu lực, Chủ thương hiệu vào Cấu hình → Cấu hình báo giá và tắt Hiển thị hiệu lực báo giá.',
            'Khi hiệu lực đang bật, kiểm tra ngày hết hạn trước khi chuyển đơn.',
            'Đối chiếu cả chiết khấu từng dòng và chiết khấu toàn báo giá trước khi gửi khách.',
            'Nếu giá bán đã thay đổi, xác nhận lại với quản lý trước khi dùng báo giá cũ.',
            'Không sửa trực tiếp đơn đã chốt nếu doanh nghiệp yêu cầu lưu lịch sử báo giá ban đầu.',
            'Đơn hàng chuyển từ báo giá sẽ giữ lại thông tin báo giá gốc để truy xuất.',
        ],
    },
    {
        'title': 'Tạo đơn bán hàng hoặc POS nhanh',
        'goal': 'Ghi nhận giao dịch bán hàng, trừ tồn kho, theo dõi thanh toán và in chứng từ cho khách.',
        'steps': [
            'Mở Bán hàng / BG hoặc POS Bán hàng nếu cửa hàng bật POS.',
            'Kiểm tra đúng cửa hàng, kho bán và tài khoản nhân viên đang đăng nhập.',
            'Chọn khách hàng nếu cần lưu lịch sử; với khách lẻ có thể dùng khách mặc định theo quy trình cửa hàng.',
            'Chọn địa chỉ giao hàng đã lưu của khách để tự lấy SĐT tại điểm nhận, hoặc nhập địa chỉ và SĐT khác cho riêng đơn này.',
            'Tìm sản phẩm bằng một phần tên, mã, barcode, quy cách hoặc danh mục; sau đó thêm sản phẩm, biến thể, combo hoặc dịch vụ vào đơn.',
            'Có thể đổi thứ tự STT và cuộn riêng vùng dòng hàng khi đơn dài.',
            'Nhập số lượng và chiết khấu từng dòng theo % hoặc số tiền; nhập tiếp chiết khấu toàn đơn, phí giao hàng, chi phí khác và ghi chú.',
            'Chọn phương thức thanh toán, ngày thanh toán (có thể là ngày trong quá khứ nhưng không được sau hôm nay), số tiền đã thu rồi lưu đơn.',
            'Nếu muốn tạo đơn tương tự, chọn Sao chép tại danh sách hoặc Xem nhanh; hệ thống tạo bản nháp mới và không sao chép khoản đã thu.',
            'In hóa đơn A4, phiếu xuất hoặc hóa đơn K80. Khi đơn đã Xuất kho/Hoàn thành, chọn Phiếu bảo hành, nhập serial/lô rồi bấm Lưu & In.',
        ],
        'checks': [
            'Nếu tồn kho không đủ, kiểm tra cấu hình có cho phép bán âm hay không.',
            'Trong kết quả tìm sản phẩm, Giá nhập và Giá vốn chỉ hiện với Chủ thương hiệu, Giám đốc hoặc Kế toán; tài khoản bán hàng thông thường chỉ thấy Giá bán.',
            'Cảnh báo bán dưới giá vốn không chặn lưu; cần xác nhận đây là giá được duyệt, hàng tặng hoặc khuyến mãi.',
            'Nếu khách trả thiếu, đơn phải thể hiện đúng công nợ còn lại.',
            'Phiếu bảo hành chỉ lưu được cho sản phẩm thuộc đơn đã xuất kho và số lượng bảo hành không vượt số lượng đã bán.',
            'Nếu đơn cần duyệt, nhân viên không tự ý giao hàng trước khi trạng thái được duyệt.',
            'Kiểm tra lại tổng tiền trước khi lưu để tránh sai số tiền.',
        ],
    },
    {
        'title': 'Xử lý trả hàng, đổi hàng hoặc hoàn tiền',
        'goal': 'Ghi nhận hàng quay lại kho, tiền hoàn/cấn trừ và lịch sử giao dịch minh bạch.',
        'steps': [
            'Nếu chưa có quỹ sử dụng để hoàn tiền, vào Tài chính → Sổ quỹ và tạo quỹ/tài khoản tương ứng (ví dụ: Quỹ tiền mặt, Tài khoản ngân hàng hoặc Ví điện tử).',
            'Vào Cài đặt → Phương thức TT, bấm Sửa phương thức hoàn tiền và chọn quỹ tại trường Tài khoản mặc định, sau đó bấm Lưu. Đây là quỹ hệ thống tự chọn khi dùng phương thức đó.',
            'Tìm đơn gốc hoặc khách hàng liên quan tới giao dịch trả hàng.',
            'Vào chức năng Trả hàng, chọn sản phẩm cần trả và số lượng.',
            'Nhập lý do trả (hàng hỏng, sai size, khách đổi ý, v.v.).',
            'Kiểm tra tình trạng sản phẩm: có nhập lại kho, hỏng, đổi size/mẫu hay cấn trừ đơn mới.',
            'Xác nhận số tiền hoàn, số tiền cấn trừ hoặc công nợ điều chỉnh.',
            'Khi chọn Phương thức hoàn tiền, hệ thống tự điền quỹ mặc định đã cấu hình. Nếu phương thức chưa có quỹ mặc định, chọn Tài khoản/quỹ hoàn tiền trực tiếp trên phiếu trước khi lưu.',
            'Lưu phiếu trả hàng và in chứng từ nếu cửa hàng yêu cầu khách ký xác nhận.',
        ],
        'checks': [
            'Không trả vượt số lượng đã bán trên đơn gốc.',
            'Nếu hàng lỗi không nhập lại kho bán được, cần ghi chú rõ để xử lý tồn kho.',
            'Kế toán phải đối chiếu khoản hoàn tiền với sổ quỹ hoặc phương thức thanh toán.',
            'Nếu xuất hiện thông báo “Phương thức hoàn tiền chưa có tài khoản/quỹ mặc định để ghi nhận phiếu chi”, kiểm tra lại Cài đặt → Phương thức TT hoặc chọn quỹ trực tiếp trên phiếu.',
            'Kiểm tra lại tồn kho sau khi xác nhận phiếu trả.',
        ],
    },
    {
        'title': 'Nhập hàng từ nhà cung cấp',
        'goal': 'Cập nhật tồn kho, giá nhập, nhà cung cấp và lịch sử mua hàng để tính giá vốn chính xác hơn.',
        'steps': [
            'Tạo hoặc chọn nhà cung cấp trước khi nhập hàng.',
            'Lập đơn đặt hàng nhập nếu cần quản lý hàng đang chờ về.',
            'Khi nhận hàng, tạo phiếu nhập, chọn kho nhận và nhà cung cấp.',
            'Tại ô Chọn sản phẩm để thêm, gõ một phần tên, mã, barcode hoặc quy cách; có thể gõ không dấu và không cần nhập đủ nguyên tên.',
            'Chọn sản phẩm để thêm một dòng vào bảng chi tiết. Nếu chọn lại sản phẩm/biến thể đã có, hệ thống đưa con trỏ về số lượng thay vì tạo dòng trùng.',
            'Nhập số lượng thực nhận, sửa Giá nhập trên từng dòng nếu giá thực tế khác giá gợi ý và ghi chú chênh lệch nếu có.',
            'Lưu phiếu nhập để hệ thống cập nhật tồn kho và lịch sử giá nhập.',
            'Vào Báo cáo → BC Nhập hàng, chọn từ đầu tháng đến cuối tháng hoặc ngày hiện tại để xem tổng hợp theo từng nhà cung cấp.',
            'Có thể lọc một nhà cung cấp và Xuất Excel; sheet Tổng hợp NCC ghi số phiếu hoàn thành và tổng tiền hàng.',
        ],
        'checks': [
            'Giá nhập phải nhập đúng trước thuế/sau thuế theo quy định nội bộ của doanh nghiệp.',
            'Số lượng thực nhận có thể khác số lượng đặt, cần ghi chú để đối chiếu nhà cung cấp.',
            'Không nhập nhầm kho nếu doanh nghiệp có nhiều cửa hàng hoặc kho tổng.',
            'Nếu để trống mã, hệ thống tự sinh mã tiếp theo và không dùng lại mã của phiếu đã xóa; nếu nhập tay mã trùng, cần đổi sang mã khác theo thông báo.',
            'Kiểm tra lại tổng tiền phiếu nhập trước khi xác nhận.',
            'Bảng tổng hợp nhà cung cấp chỉ cộng các phiếu ở trạng thái Hoàn thành; phiếu nháp hoặc hủy không được tính vào tiền hàng.',
        ],
    },
    {
        'title': 'Kiểm hàng và điều chỉnh tồn kho',
        'goal': 'Đối chiếu tồn hệ thống với tồn thực tế, phát hiện thất thoát, sai lệch nhập xuất hoặc hàng hỏng.',
        'steps': [
            'Vào Kho & Sản phẩm → Quản lý kho để xem bảng tồn của toàn bộ sản phẩm trong phạm vi cửa hàng được quản lý.',
            'Đọc cột Tồn tối thiểu và Tồn tối đa để biết ngưỡng của sản phẩm; cột Tồn kho là số lượng thực tế đang ghi nhận; cột Có thể bán bằng Tồn kho trừ số lượng đang giữ cho đơn chưa xuất kho.',
            'Bấm Sửa ở cột Thao tác để chỉnh tồn theo từng kho hoặc xem lịch sử nhập của sản phẩm.',
            'Tại Ngưỡng tồn của sản phẩm, nhập Tồn kho tối thiểu để cảnh báo và tính số lượng cần nhập; nhập Tồn kho tối đa để cảnh báo vượt ngưỡng, hoặc để 0 nếu không giới hạn. Hai ngưỡng áp dụng chung cho sản phẩm.',
            'Dùng bộ chọn tại cột Có thể bán hoặc Tồn kho để sắp xếp tăng/giảm; chọn Tồn kho âm để chỉ xem các mã đang âm kho.',
            'Chọn kho cần kiểm, nhóm sản phẩm hoặc danh sách sản phẩm cần kiểm.',
            'Đếm số lượng thực tế tại kệ, kho hoặc phòng lưu trữ.',
            'Nhập số lượng thực tế vào phiếu kiểm hàng.',
            'Kiểm tra cột chênh lệch, ghi lý do: bán thiếu ghi nhận, nhập thiếu, hỏng, mất, trả hàng hoặc chuyển kho chưa cập nhật.',
            'Chỉ xác nhận phiếu kiểm khi quản lý đã đồng ý với chênh lệch.',
            'Sau khi xác nhận, kiểm tra lại tồn kho và báo cáo tồn.',
            'Trên BC Kho, bấm thẻ Cảnh báo hoặc chọn bộ lọc thiếu/vượt tồn để xem các mã cần xử lý và cột Cần nhập tối thiểu.',
        ],
        'checks': [
            'Các đơn ở trạng thái Đơn hàng, Đang xử lý hoặc Đang đóng gói sẽ giữ hàng; vì vậy Có thể bán có thể thấp hơn Tồn kho.',
            'Nếu không có đơn đang giữ hàng, Có thể bán sẽ bằng Tồn kho.',
            'Tồn combo được tính từ khả năng đáp ứng của các thành phần và không chỉnh trực tiếp.',
            'Nếu cần nhập tồn âm, Chủ thương hiệu phải bật Cho phép tồn âm trong cấu hình kinh doanh; khi cấu hình đang tắt, hệ thống không ghi một phần dữ liệu âm.',
            'Nên kiểm các sản phẩm bán chạy, giá trị cao hoặc hay lệch tồn trước.',
            'Không dùng kiểm hàng để che lỗi quy trình; cần ghi chú nguyên nhân để cải thiện vận hành.',
            'Nếu chênh lệch lớn, nên kiểm lại lần hai trước khi xác nhận.',
            'Cần khai báo tồn tối thiểu/tối đa trên sản phẩm để cảnh báo và số lượng đề xuất nhập có ý nghĩa.',
            'Tồn kho tối thiểu nhận số nguyên và có thể âm; Tồn kho tối đa nhận số nguyên không âm, phải bằng 0 hoặc lớn hơn hay bằng mức tối thiểu.',
            'Phiếu kiểm hàng đã xác nhận không thể sửa, chỉ có thể tạo phiếu bổ sung.',
        ],
    },
    {
        'title': 'Chuyển kho giữa cửa hàng hoặc kho tổng',
        'goal': 'Điều chuyển hàng đúng điểm bán, giảm thiếu hàng cục bộ và giữ lịch sử luân chuyển rõ ràng.',
        'steps': [
            'Vào Chuyển hàng nếu doanh nghiệp có nhiều kho/cửa hàng.',
            'Chọn kho xuất, kho nhận, ngày chuyển và người phụ trách.',
            'Thêm sản phẩm cần chuyển, số lượng chuyển và ghi chú lý do chuyển.',
            'Kiểm tra tồn kho xuất có đủ số lượng hay không.',
            'Lưu phiếu chuyển và đối chiếu hàng thực nhận tại kho nhận.',
            'Sau khi hoàn tất, kiểm tra tồn ở cả kho xuất và kho nhận.',
        ],
        'checks': [
            'Không chuyển nhầm kho nhận.',
            'Hàng đang vận chuyển cần có người chịu trách nhiệm nhận bàn giao.',
            'Nếu kho nhận nhận thiếu, phải ghi chú và báo quản lý trước khi xác nhận số thực nhận.',
            'Kiểm tra lại báo cáo tồn kho sau khi phiếu chuyển được xác nhận.',
        ],
    },
    {
        'title': 'Ghi nhận phiếu thu, phiếu chi và công nợ',
        'goal': 'Theo dõi dòng tiền thực tế, số tiền đã thu, khoản còn nợ và chi phí vận hành.',
        'steps': [
            'Khi khách thanh toán, tạo phiếu thu hoặc ghi nhận thanh toán ngay trên đơn hàng.',
            'Chọn đúng khách hàng, đơn hàng liên quan, số tiền thu và phương thức thanh toán.',
            'Khi phát sinh chi phí, tạo phiếu chi với danh mục chi, người nhận, số tiền và ghi chú.',
            'Kiểm tra sổ quỹ để xem dòng tiền vào/ra theo ngày.',
            'Đối chiếu các đơn còn nợ với danh sách phiếu thu bổ sung.',
        ],
        'checks': [
            'Không ghi nhận một khoản thu hai lần cho cùng một đơn.',
            'Phiếu chi nên có lý do rõ ràng để báo cáo tài chính không bị mơ hồ.',
            'Cuối ngày phải đối chiếu tiền mặt, chuyển khoản và tổng phiếu thu chi.',
            'Kiểm tra lại sổ quỹ trước khi đóng ca để đảm bảo số liệu khớp.',
        ],
    },
    {
        'title': 'Xem doanh thu, giá vốn, lợi nhuận và đơn lỗ theo ngày',
        'goal': 'Kiểm tra kết quả kinh doanh trong một ngày hoặc khoảng ngày, đồng thời xác định từng đơn và sản phẩm đang bán lỗ.',
        'steps': [
            'Đăng nhập bằng tài khoản Chủ thương hiệu, Giám đốc hoặc Kế toán. Đây là các vai trò được phép xem Báo cáo bán hàng.',
            'Trên thanh menu bên trái, vào Báo cáo và chọn BC Bán hàng.',
            'Tại Bộ lọc, nhập Từ ngày và Đến ngày. Ví dụ muốn kiểm tra ngày 11 và 12/07 thì chọn Từ ngày 11/07, Đến ngày 12/07.',
            'Giữ Phạm vi đơn là "Đã xuất kho + Hoàn thành" để xem doanh thu đã thực hiện. Nếu cần kiểm tra cả đơn đang xử lý nhưng chưa hủy, chọn "Tất cả đơn chưa hủy".',
            'Để xem toàn bộ kết quả, giữ bộ lọc Lợi nhuận là "Tất cả". Để chỉ xem đơn lỗ, chọn "Báo lỗ" rồi nhấn "Xem báo cáo".',
            'Mở tab Tổng quan để xem tổng số đơn, doanh thu, giá vốn thuần, lợi nhuận gộp, công nợ và số đơn báo lỗ trong khoảng ngày đã chọn.',
            'Mở tab Tổng hợp ngày để đối chiếu riêng từng ngày: tiền hàng, doanh thu, doanh thu thuần, giá vốn thuần, lợi nhuận gộp và tỷ suất lợi nhuận.',
            'Mở tab Theo đơn để xem từng đơn. Đơn lỗ được đánh dấu màu đỏ; các cột Sản phẩm lỗ, Doanh thu, Giá vốn và Lợi nhuận cho biết nguyên nhân và mức lỗ.',
            'Bấm vào mã đơn hoặc nút "Mở đơn lỗ" để kiểm tra chi tiết đơn hàng. Có thể nhấn "Xuất Excel" nếu cần gửi hoặc lưu báo cáo.',
        ],
        'checks': [
            'Khoảng ngày trên BC Bán hàng hiện được lọc theo Ngày đặt hàng, không phải ngày khách chuyển khoản, ngày ghi phiếu thu hoặc ngày hoàn thành đơn.',
            'Doanh thu của đơn được tính từ tiền hàng sau chiết khấu, cộng phí vận chuyển và chi phí khác; lợi nhuận bằng doanh thu trừ giá vốn.',
            'Muốn số liệu lãi/lỗ chính xác, sản phẩm phải có giá vốn hoặc giá nhập đúng và đơn hàng phải ghi nhận đủ số lượng, chiết khấu, phí phát sinh và trả hàng.',
            'Nếu không thấy dữ liệu, kiểm tra lại khoảng ngày, Phạm vi đơn, cửa hàng và bộ lọc Lợi nhuận trước khi kết luận báo cáo bị thiếu.',
        ],
    },
    {
        'title': 'Xem báo cáo và ra quyết định',
        'goal': 'Biến dữ liệu bán hàng, kho, khách hàng và tài chính thành thông tin quản trị dễ hiểu.',
        'steps': [
            'Vào nhóm Báo cáo trên sidebar.',
            'Chọn báo cáo phù hợp: bán hàng, nhập hàng, tồn kho, tài chính, khách hàng hoặc nhân viên bán hàng.',
            'Chọn khoảng thời gian (ngày, tuần, tháng, tùy chỉnh), cửa hàng, kho hoặc bộ lọc liên quan.',
            'Tại BC Nhập hàng, xem bảng Tổng hợp theo nhà cung cấp để biết số phiếu hoàn thành và tổng tiền hàng; có thể lọc riêng một nhà cung cấp.',
            'Tại BC Kho, chọn riêng Danh mục sản phẩm hoặc Loại sản phẩm; khi đã chọn danh mục, danh sách loại chỉ còn các loại trực thuộc danh mục đó.',
            'Đọc Tổng giá trị tồn theo công thức tổng của từng sản phẩm có tồn dương × giá vốn. Tồn âm vẫn hiển thị để xử lý nhưng không khấu trừ giá trị hàng còn lại.',
            'Bấm thẻ Cảnh báo để lọc hàng dưới tồn tối thiểu hoặc trên tồn tối đa và xem số lượng cần nhập bổ sung.',
            'Đọc số tổng trước, sau đó xem chi tiết theo sản phẩm, khách hàng, nhân viên hoặc chứng từ.',
            'Đối chiếu báo cáo với sổ quỹ, tồn kho và đơn hàng khi có số liệu bất thường.',
            'Xuất dữ liệu (Excel, PDF) nếu cần gửi kế toán, chủ doanh nghiệp hoặc lưu hồ sơ nội bộ.',
        ],
        'checks': [
            'Báo cáo chỉ chính xác khi đơn hàng, nhập hàng và thu chi được nhập đúng thời điểm.',
            'BC Nhập hàng theo nhà cung cấp chỉ tính tiền của phiếu nhập Hoàn thành trong khoảng ngày đã chọn.',
            'File Excel BC Kho giữ bộ lọc Danh mục và Loại sản phẩm đang chọn; giá trị tồn của dòng âm bằng 0.',
            'Nếu doanh thu và tiền thu lệch nhau, kiểm tra công nợ và phương thức thanh toán.',
            'Nếu tồn kho âm hoặc lệch, kiểm tra đơn bán, phiếu nhập, phiếu trả và phiếu kiểm hàng.',
        ],
    },
]

IMPLEMENTATION_CHECKLIST = [
    {
        'phase': 'Trước triển khai',
        'items': [
            'Xác định lĩnh vực của khách: bán lẻ, F&B, spa, thời trang, nhà thuốc hoặc mô hình tùy chỉnh.',
            'Chốt danh sách module sẽ dùng ngay trong giai đoạn đầu và module để mở rộng sau.',
            'Thu thập dữ liệu sản phẩm/dịch vụ (tên, mã, đơn vị tính, giá bán, giá nhập, nhà cung cấp, kỳ hạn/chính sách bảo hành và ảnh).',
            'Thu thập danh sách khách hàng, địa chỉ/điểm nhận, nhà cung cấp, tồn kho đầu kỳ và tài khoản nhân viên.',
            'Xác định quy trình bán hàng: bán trực tiếp, báo giá trước, duyệt đơn, giao hàng, trả hàng, công nợ.',
            'Xác định mẫu in: hóa đơn K80, A4, phiếu xuất, phiếu bảo hành, báo giá hoặc chứng từ nội bộ.',
        ],
    },
    {
        'phase': 'Trong lúc cấu hình',
        'items': [
            'Tạo thương hiệu, cửa hàng, kho, người quản lý và thông tin liên hệ.',
            'Bật đúng mô hình kinh doanh và các module cần thiết trong màn hình Mô hình kinh doanh.',
            'Tạo tài khoản người dùng theo vai trò, gán cửa hàng và phân quyền phù hợp.',
            'Nhập danh mục sản phẩm, dịch vụ, nhóm khách hàng, nhà cung cấp và phương thức thanh toán.',
            'Nhập tồn đầu kỳ hoặc phiếu nhập đầu tiên để hệ thống có dữ liệu kho chính xác.',
            'Khai báo các nhãn hàng dùng trên chứng từ và đặt Thứ tự ưu tiên; dùng số nhỏ cho nhãn cần xuất hiện trước.',
            'Cấu hình mẫu in, máy in và phương thức thanh toán mặc định.',
        ],
    },
    {
        'phase': 'Chạy thử',
        'items': [
            'Tạo một khách hàng mẫu và một đơn bán mẫu từ đầu tới cuối.',
            'Thử báo giá, chiết khấu theo tiền/%, chuyển hoặc sao chép đơn, thanh toán, in hóa đơn và kiểm tra công nợ.',
            'Thử nhập hàng, kiểm hàng, trả hàng và xem tồn kho sau mỗi thao tác.',
            'Thử lưu/in phiếu bảo hành từ một đơn đã xuất kho.',
            'Thử phiếu thu, phiếu chi, sổ quỹ, BC Bán hàng, BC Nhập hàng theo NCC và cảnh báo trên BC Kho.',
            'Ghi lại các điểm chưa đúng quy trình thực tế để điều chỉnh trước khi vận hành thật.',
        ],
    },
    {
        'phase': 'Bàn giao',
        'items': [
            'Gửi tài khoản đăng nhập, tài liệu hướng dẫn đúng lĩnh vực và checklist thao tác theo vai trò.',
            'Đào tạo riêng cho chủ doanh nghiệp, quản lý, bán hàng, kho và kế toán.',
            'Yêu cầu khách tự tạo lại một quy trình bán hàng hoàn chỉnh trên tài khoản demo.',
            'Chốt ngày bắt đầu nhập dữ liệu thật và người chịu trách nhiệm hỗ trợ trong ngày đầu.',
            'Sau 3-7 ngày, rà soát báo cáo, tồn kho, công nợ và các lỗi thao tác thường gặp.',
        ],
    },
]

TROUBLESHOOTING_GUIDES = [
    {
        'problem': 'Không thấy menu hoặc chức năng cần dùng',
        'causes': [
            'Tài khoản chưa được phân quyền đúng vai trò.',
            'Module đó chưa được bật trong Mô hình kinh doanh.',
            'Người dùng đang đăng nhập nhầm cửa hàng hoặc tài khoản.',
        ],
        'fixes': [
            'Chủ thương hiệu kiểm tra lại tài khoản trong Quản lý người dùng.',
            'Kiểm tra màn hình Mô hình kinh doanh để bật module cần dùng.',
            'Đăng xuất và đăng nhập lại bằng đúng tài khoản được cấp.',
        ],
    },
    {
        'problem': 'Tồn kho không khớp thực tế',
        'causes': [
            'Chưa nhập tồn đầu kỳ hoặc nhập nhầm kho.',
            'Có đơn bán, trả hàng, chuyển kho hoặc phiếu nhập chưa được ghi nhận.',
            'Nhân viên bán âm hoặc kiểm hàng chưa ghi rõ lý do chênh lệch.',
        ],
        'fixes': [
            'Kiểm tra lịch sử nhập, bán, trả hàng và chuyển kho của sản phẩm.',
            'Lọc theo đúng kho/cửa hàng trước khi kết luận lệch tồn.',
            'Tạo phiếu kiểm hàng có ghi chú nguyên nhân nếu cần điều chỉnh.',
        ],
    },
    {
        'problem': 'Doanh thu và tiền thực thu không bằng nhau',
        'causes': [
            'Có đơn khách chưa thanh toán đủ nên phát sinh công nợ.',
            'Một số giao dịch dùng chuyển khoản, thẻ hoặc ví điện tử chưa về tiền.',
            'Phiếu thu hoặc phiếu chi được nhập thiếu, nhập trùng hoặc chọn sai ngày.',
        ],
        'fixes': [
            'Xem danh sách đơn còn nợ và phiếu thu liên quan.',
            'Đối chiếu báo cáo bán hàng với sổ quỹ theo cùng khoảng thời gian.',
            'Kiểm tra phương thức thanh toán của từng đơn trước khi chốt ca.',
        ],
    },
    {
        'problem': 'Không in được hóa đơn hoặc chứng từ',
        'causes': [
            'Máy in chưa được cấu hình hoặc chưa chọn đúng khổ giấy.',
            'Trình duyệt chặn cửa sổ in hoặc thiết bị chưa kết nối máy in.',
            'Mẫu in chưa phù hợp với loại chứng từ đang dùng.',
        ],
        'fixes': [
            'Kiểm tra Cài đặt máy in và thử in test.',
            'Cho phép pop-up/in trên trình duyệt nếu bị chặn.',
            'Chọn đúng mẫu K80, A4, phiếu xuất, báo giá hoặc hóa đơn theo nhu cầu.',
        ],
    },
    {
        'problem': 'Báo cáo thiếu dữ liệu',
        'causes': [
            'Chọn sai khoảng thời gian, cửa hàng, kho hoặc bộ lọc.',
            'Đơn hàng chưa lưu/chưa hoàn tất hoặc dữ liệu chưa được nhập đúng ngày.',
            'Người dùng không có quyền xem phạm vi báo cáo đó.',
        ],
        'fixes': [
            'Đặt lại bộ lọc và kiểm tra ngày bắt đầu/kết thúc.',
            'Mở danh sách đơn hàng, phiếu nhập hoặc phiếu thu chi để đối chiếu dữ liệu gốc.',
            'Nhờ chủ thương hiệu kiểm tra lại quyền xem báo cáo.',
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
            {'title': 'Bán hàng tại shop', 'body': 'Nhân viên chọn đúng size/màu, áp dụng giảm giá nếu có, ghi nhận khách hàng và thanh toán.'},
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

FIELD_DEEP_DIVES = {
    'retail': {
        'title': 'Hướng dẫn chi tiết cho mô hình bán lẻ',
        'sections': [
            {
                'title': 'Danh mục và mã hàng',
                'items': [
                    'Nên thống nhất quy tắc mã hàng trước khi nhập dữ liệu: theo nhóm hàng, thương hiệu, kích thước hoặc mã vạch có sẵn.',
                    'Mỗi sản phẩm cần có tên dễ tìm, đơn vị tính, nhóm hàng, giá bán, giá nhập tham khảo và kho mặc định.',
                    'Với hàng có nhiều phiên bản, dùng biến thể để tách màu, dung tích, cấu hình, size hoặc quy cách đóng gói.',
                    'Vị trí lưu kho/kệ nên được nhập rõ để nhân viên tìm hàng nhanh khi bán và kiểm kê.',
                    'Thêm ảnh sản phẩm để nhân viên bán hàng và quản lý dễ nhận diện.',
                ],
            },
            {
                'title': 'Bán tại quầy',
                'items': [
                    'Nhân viên mở POS, tìm sản phẩm bằng tên/mã/mã vạch, thêm vào giỏ và kiểm tra số lượng tồn.',
                    'Nếu khách là khách thân thiết, chọn khách trước khi thanh toán để lưu lịch sử mua.',
                    'Khi có giảm giá, nhân viên cần ghi đúng lý do hoặc xin quản lý duyệt theo quy định nội bộ.',
                    'Sau khi khách thanh toán, in hóa đơn K80 hoặc chứng từ phù hợp, đồng thời hệ thống tự cập nhật tồn kho.',
                    'Với đơn lớn hoặc đơn giao hàng, cần nhập địa chỉ giao và phí giao hàng nếu có.',
                ],
            },
            {
                'title': 'Kiểm soát cuối ngày',
                'items': [
                    'Đối chiếu số đơn trong ngày với tổng tiền mặt, chuyển khoản và các phương thức thanh toán khác.',
                    'Kiểm tra danh sách đơn còn nợ, đơn trả hàng và phiếu chi phát sinh trong ngày.',
                    'Xem top sản phẩm bán chạy, tồn kho thấp và mặt hàng cần nhập bổ sung.',
                    'Với sản phẩm dễ thất thoát, nên kiểm tồn nhanh cuối ngày hoặc cuối ca.',
                    'Đóng ca và xác nhận báo cáo cuối ngày trước khi nghỉ.',
                ],
            },
        ],
    },
    'fnb': {
        'title': 'Hướng dẫn chi tiết cho nhà hàng / quán cafe',
        'sections': [
            {
                'title': 'Chuẩn bị menu và bàn',
                'items': [
                    'Tạo danh mục món theo nhóm: đồ uống, món chính, topping, combo, hàng bán kèm hoặc nguyên vật liệu.',
                    'Bật POS bán nhanh và quản lý bàn nếu quán phục vụ tại chỗ.',
                    'Đặt tên bàn/khu vực rõ ràng để nhân viên chọn đúng bàn, tránh gộp nhầm hóa đơn.',
                    'Nếu có nhiều ca, cần thống nhất quy trình bàn giao tiền và đơn chưa thanh toán giữa các ca.',
                    'Thêm ảnh món để nhân viên order nhanh hơn và khách dễ chọn.',
                ],
            },
            {
                'title': 'Nhận order và thanh toán',
                'items': [
                    'Nhân viên chọn bàn hoặc mở POS mang đi, thêm món, số lượng và ghi chú yêu cầu của khách (ít đường, không đá, v.v.).',
                    'Khi khách gọi thêm món, mở lại bàn đang phục vụ để cập nhật thay vì tạo đơn mới.',
                    'Khi thanh toán, kiểm tra lại toàn bộ món, giảm giá, phụ thu, phương thức thanh toán và in hóa đơn.',
                    'Đơn bán mang đi nên xử lý nhanh trên POS, hạn chế thao tác nhiều bước.',
                    'Nếu khách hủy món, cần ghi lý do để quản lý theo dõi.',
                ],
            },
            {
                'title': 'Đối soát ca bán',
                'items': [
                    'Cuối ca kiểm tra bàn còn mở, đơn đã thanh toán, đơn hủy và đơn chỉnh sửa.',
                    'Đối chiếu tiền mặt thực tế với phiếu thu và doanh thu theo phương thức thanh toán.',
                    'Theo dõi món bán chạy, nguyên vật liệu tồn thấp và chi phí phát sinh trong ngày.',
                    'Nếu có thất thoát nguyên liệu, dùng kiểm hàng để ghi nhận và tìm nguyên nhân.',
                    'Đóng ca và xác nhận báo cáo trước khi bàn giao cho ca tiếp theo.',
                ],
            },
        ],
    },
    'spa': {
        'title': 'Hướng dẫn chi tiết cho spa / dịch vụ',
        'sections': [
            {
                'title': 'Thiết lập dịch vụ và nguồn lực',
                'items': [
                    'Tạo danh sách dịch vụ, thời lượng dự kiến, giá bán, nhóm dịch vụ và mô tả nếu cần tư vấn.',
                    'Khai báo nhân viên/kỹ thuật viên, phòng, giường hoặc khu vực phục vụ.',
                    'Nếu có liệu trình nhiều buổi, nên thống nhất cách ghi chú số buổi còn lại và lịch hẹn tiếp theo.',
                    'Khách hàng nên được lưu đầy đủ số điện thoại, ngày sinh, nhu cầu, tình trạng da/sức khỏe nếu phù hợp quy trình tư vấn.',
                ],
            },
            {
                'title': 'Đặt lịch và phục vụ',
                'items': [
                    'Lễ tân tạo khách, chọn dịch vụ, thời gian, nhân viên phụ trách, phòng và ghi chú nhu cầu.',
                    'Trước giờ hẹn, kiểm tra lịch để tránh trùng phòng, trùng kỹ thuật viên hoặc thiếu thời gian chuẩn bị.',
                    'Khi khách đến, cập nhật trạng thái lịch hẹn và ghi nhận dịch vụ phát sinh nếu khách đổi gói.',
                    'Sau khi hoàn tất, tạo thanh toán và ghi chú chăm sóc sau dịch vụ.',
                ],
            },
            {
                'title': 'Chăm sóc khách quay lại',
                'items': [
                    'Dùng lịch sử dịch vụ để tư vấn gói phù hợp, nhắc lịch tái khám/tái chăm sóc hoặc bán thêm sản phẩm.',
                    'Lọc khách lâu chưa quay lại để tạo danh sách gọi điện chăm sóc.',
                    'Theo dõi doanh thu theo dịch vụ và hiệu suất kỹ thuật viên để điều phối lịch hợp lý.',
                    'Cuối ngày đối chiếu lịch đã phục vụ với tiền thu và công nợ dịch vụ.',
                ],
            },
        ],
    },
    'fashion': {
        'title': 'Hướng dẫn chi tiết cho thời trang / giày dép',
        'sections': [
            {
                'title': 'Sản phẩm nhiều size, màu',
                'items': [
                    'Tạo sản phẩm cha theo mẫu, sau đó tách biến thể theo size, màu, chất liệu hoặc phiên bản.',
                    'Mỗi biến thể nên có mã riêng để bán, đổi trả và kiểm kho chính xác.',
                    'Khi nhập hàng, nhập đúng từng biến thể để tránh tình trạng tổng tồn đúng nhưng từng size/màu bị sai.',
                    'Nên thêm ảnh đại diện sản phẩm để nhân viên bán hàng tìm nhanh hơn.',
                ],
            },
            {
                'title': 'Bán hàng và đổi trả',
                'items': [
                    'Nhân viên phải chọn đúng size/màu trước khi lưu đơn.',
                    'Nếu khách đổi size, dùng quy trình trả hàng/đổi hàng để tồn kho quay lại đúng biến thể.',
                    'Giảm giá theo chương trình cần được ghi nhận rõ để báo cáo doanh thu và lợi nhuận không bị hiểu sai.',
                    'Với đơn online, nên ghi chú kênh bán, phí giao hàng và trạng thái đóng gói.',
                ],
            },
            {
                'title': 'Điều chuyển và xả tồn',
                'items': [
                    'Theo dõi tồn chậm theo mẫu, size, màu và cửa hàng.',
                    'Dùng chuyển kho để đưa hàng từ nơi bán chậm sang nơi có nhu cầu cao.',
                    'Trước chiến dịch giảm giá, xuất danh sách tồn để chọn nhóm hàng cần xả.',
                    'Sau chương trình, xem báo cáo để biết mẫu nào bán tốt và mẫu nào cần dừng nhập.',
                ],
            },
        ],
    },
    'pharmacy': {
        'title': 'Hướng dẫn chi tiết cho nhà thuốc',
        'sections': [
            {
                'title': 'Khai báo thuốc và vật tư',
                'items': [
                    'Tạo danh mục theo nhóm thuốc, thực phẩm chức năng, vật tư y tế hoặc hàng chăm sóc sức khỏe.',
                    'Nhập rõ đơn vị tính, quy cách, vị trí kệ, giá bán và giá nhập.',
                    'Nếu một mặt hàng có nhiều quy cách, nên tách biến thể hoặc sản phẩm riêng theo quy định quản lý nội bộ.',
                    'Nhà thuốc nên kiểm tra kỹ tên sản phẩm để tránh nhầm hàng có tên gần giống nhau.',
                ],
            },
            {
                'title': 'Bán tại quầy',
                'items': [
                    'Nhân viên tìm sản phẩm, kiểm tồn, chọn đúng quy cách và số lượng trước khi thanh toán.',
                    'Nếu khách mua lại thường xuyên, chọn khách để lưu lịch sử mua.',
                    'Với hàng cần tư vấn, ghi chú thông tin cần theo dõi theo quy trình của nhà thuốc.',
                    'Sau thanh toán, in hóa đơn nếu khách cần hoặc lưu giao dịch để đối chiếu cuối ngày.',
                ],
            },
            {
                'title': 'Kiểm tồn và nhập hàng',
                'items': [
                    'Theo dõi tồn thấp để đặt hàng kịp thời, đặc biệt với nhóm bán chạy.',
                    'Khi nhập hàng, kiểm tra số lượng, giá nhập và nhà cung cấp trước khi lưu phiếu.',
                    'Kiểm kê định kỳ các mặt hàng giá trị cao hoặc dễ nhầm quy cách.',
                    'Đối chiếu báo cáo nhập, bán và tồn để phát hiện sai lệch sớm.',
                ],
            },
        ],
    },
    'custom': {
        'title': 'Hướng dẫn chi tiết cho mô hình tùy chỉnh',
        'sections': [
            {
                'title': 'Khảo sát trước khi cấu hình',
                'items': [
                    'Ghi lại quy trình thực tế của khách: bán trực tiếp, bán theo báo giá, bán dịch vụ, đặt lịch, quản lý bàn hay quản lý kho.',
                    'Xác định dữ liệu nào bắt buộc phải có trước ngày chạy thật và dữ liệu nào có thể bổ sung sau.',
                    'Xác định ai là người tạo đơn, ai duyệt, ai thu tiền, ai nhập kho và ai xem báo cáo.',
                    'Chốt thuật ngữ hiển thị với khách để tài liệu đào tạo dễ hiểu.',
                ],
            },
            {
                'title': 'Cấu hình theo module',
                'items': [
                    'Bật các module cần dùng trong giai đoạn đầu, tránh bật quá nhiều làm nhân viên rối.',
                    'Nếu có nghiệp vụ đặc thù, mô tả rõ cách dùng module hiện có để đáp ứng quy trình đó.',
                    'Tạo nhóm quyền theo vai trò thật trong doanh nghiệp thay vì tạo một tài khoản dùng chung.',
                    'Chuẩn hóa danh mục trước khi nhập dữ liệu lớn để hạn chế sửa lại nhiều lần.',
                ],
            },
            {
                'title': 'Đào tạo và mở rộng',
                'items': [
                    'Đào tạo theo tình huống thật của khách, không chỉ giới thiệu từng menu.',
                    'Ngày đầu chạy thật nên có người hỗ trợ theo dõi đơn, kho và thu chi.',
                    'Sau một tuần, xem báo cáo để phát hiện chỗ nhập sai hoặc quy trình chưa phù hợp.',
                    'Khi khách đã quen, có thể bật thêm module nâng cao như duyệt đơn, POS, bàn cafe, spa hoặc báo cáo nhân viên.',
                ],
            },
        ],
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
