"""Focused customer-facing usage guide for Digimart retail stores."""

RETAIL_GUIDE_META = {
    'title': 'Hướng dẫn sử dụng Digimart cho cửa hàng bán lẻ',
    'subtitle': (
        'Tài liệu thao tác từ lúc khai báo sản phẩm đến bán hàng, thu tiền, quản lý công nợ, '
        'nhập kho, trả hàng và đọc báo cáo.'
    ),
    'revision_date': '25/07/2026',
    'audience': 'Chủ cửa hàng, quản lý, nhân viên bán hàng, nhân viên kho và kế toán.',
    'scope': (
        'Tài liệu này chỉ trình bày quy trình bán lẻ. Các mô hình F&B, spa, thời trang chuyên sâu '
        'và nhà thuốc sẽ được bổ sung sau.'
    ),
}


RETAIL_ROLE_START = [
    {
        'role': 'Chủ cửa hàng / Quản lý',
        'start': 'Đọc Thiết lập ban đầu, Kho, Báo cáo và Chốt ngày.',
        'responsibility': 'Duyệt cách vận hành, phân quyền, kiểm soát tồn, công nợ và kết quả kinh doanh.',
    },
    {
        'role': 'Nhân viên bán hàng',
        'start': 'Đọc Khách hàng, Bán hàng, Thanh toán và Trả hàng.',
        'responsibility': 'Tạo đúng đơn, đúng khách, đúng sản phẩm, đúng số tiền khách trả.',
    },
    {
        'role': 'Nhân viên kho',
        'start': 'Đọc Sản phẩm, Nhập hàng, Quản lý kho và Kiểm hàng.',
        'responsibility': 'Ghi nhận đúng kho, số lượng, giá nhập và nguyên nhân chênh lệch.',
    },
    {
        'role': 'Kế toán',
        'start': 'Đọc Thanh toán, Sổ quỹ, Công nợ, BC Tài chính và BC Bán hàng.',
        'responsibility': 'Đối chiếu tiền thực thu, chứng từ thu chi, công nợ và số liệu báo cáo.',
    },
]


RETAIL_SETUP_STEPS = [
    {
        'title': '1. Khai báo cửa hàng và kho',
        'path': 'Cấu hình → Cửa hàng; Kho & Sản phẩm → Kho',
        'actions': [
            'Kiểm tra đúng tên cửa hàng, địa chỉ, số điện thoại và thông tin in hóa đơn.',
            'Mỗi điểm bán cần có ít nhất một kho xuất hàng.',
            'Nếu có kho tổng và nhiều cửa hàng, đặt tên rõ như “Kho tổng”, “Kho Cửa hàng 1”.',
        ],
        'result': 'Đơn bán, phiếu nhập, tồn kho và báo cáo được ghi nhận đúng địa điểm.',
    },
    {
        'title': '2. Tạo tài khoản và phân quyền',
        'path': 'Quản trị → Người dùng / Nhóm quyền',
        'actions': [
            'Mỗi nhân viên dùng một tài khoản riêng; không dùng chung tài khoản quản lý.',
            'Gán đúng cửa hàng và vai trò: quản lý, bán hàng, kho hoặc kế toán.',
            'Chỉ cấp quyền xem giá nhập, giá vốn và báo cáo lợi nhuận cho người cần thiết.',
        ],
        'result': 'Biết ai tạo hoặc sửa chứng từ và hạn chế lộ dữ liệu nội bộ.',
    },
    {
        'title': '3. Tạo quỹ và phương thức thanh toán',
        'path': 'Tài chính → Sổ quỹ; Cài đặt → Phương thức TT',
        'actions': [
            'Tạo các quỹ thực tế: Quỹ tiền mặt, Tài khoản ngân hàng, Ví điện tử.',
            'Gắn mỗi phương thức thanh toán với đúng tài khoản/quỹ mặc định.',
            'Đặt thứ tự ưu tiên: số nhỏ hiển thị trước, ví dụ Tiền mặt = 1, Chuyển khoản = 2.',
        ],
        'result': 'Khi thu hoặc hoàn tiền, hệ thống chọn đúng quỹ để đối soát.',
    },
    {
        'title': '4. Chuẩn hóa danh mục sản phẩm',
        'path': 'Kho & Sản phẩm → Danh mục / DS Sản phẩm',
        'actions': [
            'Thống nhất mã sản phẩm, tên, đơn vị tính, quy cách và nhóm hàng.',
            'Khai báo giá bán, giá nhập tham khảo, giá vốn, nhà cung cấp và vị trí lấy hàng.',
            'Chỉ dùng biến thể khi một sản phẩm thật sự có các phiên bản cần tách tồn như màu hoặc dung tích.',
        ],
        'result': 'Nhân viên tìm đúng hàng và báo cáo gom nhóm chính xác.',
    },
    {
        'title': '5. Nhập tồn đầu kỳ',
        'path': 'Kho & Sản phẩm → Quản lý kho / Phiếu nhập / Kiểm hàng',
        'actions': [
            'Chốt một thời điểm bắt đầu sử dụng hệ thống.',
            'Đếm tồn thực tế tại từng kho và nhập đúng số lượng vào hệ thống.',
            'Không cộng chung tồn của nhiều kho vào một kho.',
        ],
        'result': 'Tồn sau mỗi lần nhập, bán, trả hoặc chuyển kho có số gốc để đối chiếu.',
    },
    {
        'title': '6. Nhập khách hàng và nhà cung cấp',
        'path': 'Khách hàng; Kho & Sản phẩm → Nhà cung cấp',
        'actions': [
            'Nhập mã, tên, số điện thoại và nhóm khách nếu cần theo dõi lịch sử hoặc công nợ.',
            'Nhập nhà cung cấp và gắn vào sản phẩm để xem báo cáo tiêu thụ theo nhà cung cấp.',
            'Không tạo nhiều hồ sơ trùng số điện thoại hoặc trùng tên cho cùng một đối tượng.',
        ],
        'result': 'Theo dõi đúng lịch sử mua, công nợ và nguồn hàng.',
    },
    {
        'title': '7. Chạy thử trước ngày bán thật',
        'path': 'DS Đơn hàng / POS / Phiếu nhập / Báo cáo',
        'actions': [
            'Tạo một đơn bán thử có chiết khấu, thanh toán một phần và phí vận chuyển.',
            'Tạo một phiếu nhập thử, một phiếu trả hàng và một phiếu thu bổ sung.',
            'Đối chiếu lại tồn kho, công nợ, sổ quỹ và BC Bán hàng.',
        ],
        'result': 'Phát hiện sai cấu hình trước khi nhập dữ liệu thật.',
    },
]


RETAIL_OPERATION_GUIDES = [
    {
        'anchor': 'products',
        'icon': 'fas fa-box',
        'title': 'Sản phẩm và giá',
        'intro': 'Sản phẩm là dữ liệu gốc của bán hàng, kho, giá vốn và báo cáo.',
        'path': 'Kho & Sản phẩm → DS Sản phẩm',
        'steps': [
            'Bấm Thêm sản phẩm và nhập mã. Nếu để trống, hệ thống tự sinh mã tiếp theo.',
            'Nhập tên dễ tìm; tránh chỉ dùng tên viết tắt mà nhân viên mới không hiểu.',
            'Chọn danh mục, đơn vị tính, quy cách, nhà cung cấp và vị trí lấy hàng.',
            'Nhập Giá bán là giá niêm yết cho khách; Giá nhập là giá mua tham khảo; Giá vốn dùng để tính lãi.',
            'Khai báo tồn tối thiểu để cảnh báo cần nhập; tồn tối đa bằng 0 nghĩa là không giới hạn.',
            'Lưu sản phẩm, sau đó nhập tồn theo đúng kho tại Quản lý kho.',
            'Dùng Lịch sử nhập để xem các lần mua hàng và biến động giá; dùng Lịch sử kho để truy nhập, xuất, kiểm và chứng từ nguồn.',
        ],
        'checks': [
            'Mỗi mã chỉ đại diện cho một sản phẩm hoặc một biến thể.',
            'Không bỏ trống giá vốn nếu muốn báo cáo lợi nhuận có ý nghĩa.',
            'Vị trí sản phẩm được đưa lên Phiếu đóng hàng để nhân viên lấy hàng.',
            'Sản phẩm dịch vụ không làm tăng hoặc giảm tồn kho.',
        ],
    },
    {
        'anchor': 'customers',
        'icon': 'fas fa-users',
        'title': 'Khách hàng',
        'intro': 'Chỉ cần tạo khách khi muốn lưu lịch sử mua, giao hàng, bảo hành hoặc công nợ.',
        'path': 'Khách hàng → DS Khách hàng',
        'steps': [
            'Tìm theo tên hoặc số điện thoại trước khi tạo để tránh hồ sơ trùng.',
            'Chọn khách cá nhân hoặc doanh nghiệp; nhập mã, tên và số điện thoại.',
            'Khai báo khách buôn/lẻ và nhóm khách nếu cửa hàng dùng chính sách riêng.',
            'Lưu địa chỉ mặc định và các điểm nhận phụ; mỗi điểm nhận có thể có số điện thoại riêng.',
            'Khi tạo đơn, chọn đúng khách trước khi nhập thanh toán để lịch sử và công nợ được gắn đúng người.',
            'Tại DS Khách hàng, xem Tổng mua và Công nợ; dùng nút sắp xếp để ưu tiên khách mua nhiều hoặc nợ cao.',
        ],
        'checks': [
            'Đơn không gắn hồ sơ khách được hiển thị là Khách lẻ / khách vãng lai.',
            'Địa chỉ trên đơn được lưu riêng để giữ lịch sử ngay cả khi hồ sơ khách thay đổi.',
            'Không sửa hồ sơ khách A thành khách B; hãy tạo hồ sơ mới để giữ đúng lịch sử.',
        ],
    },
    {
        'anchor': 'sales',
        'icon': 'fas fa-shopping-cart',
        'title': 'Tạo và xử lý đơn bán',
        'intro': 'Một đơn đúng phải đủ khách hàng, kho xuất, sản phẩm, giá, chiết khấu, phí, thanh toán và trạng thái.',
        'path': 'Bán hàng → DS Đơn hàng hoặc POS',
        'steps': [
            'Kiểm tra đúng cửa hàng, kho xuất và ngày đặt hàng.',
            'Chọn khách hàng nếu cần theo dõi lịch sử, giao hàng hoặc công nợ.',
            'Tìm sản phẩm theo mã, tên, barcode, quy cách hoặc từ khóa không dấu.',
            'Nhập số lượng, đơn giá và chiết khấu từng dòng; kiểm tra cảnh báo tồn và cảnh báo bán dưới giá vốn.',
            'Nếu có, nhập chiết khấu chung, phí vận chuyển và chi phí khác.',
            'Chọn nhân viên bán hàng, địa chỉ giao và ghi chú cần thiết.',
            'Nhập đúng số khách trả lần đầu; không đánh dấu trả đủ nếu thực tế khách còn nợ.',
            'Lưu đơn. Khi đã giao hàng khỏi kho, chuyển sang Đã xuất kho; khi nghiệp vụ kết thúc, chuyển Hoàn thành.',
            'Có thể in hóa đơn, phiếu xuất, phiếu đóng hàng hoặc phiếu bảo hành tùy nhu cầu.',
        ],
        'checks': [
            'Báo giá, Đơn hàng, Đang xử lý và Đang đóng gói chưa phải doanh thu đã thực hiện khi dùng phạm vi báo cáo mặc định.',
            'Đã xuất kho nghĩa là hàng đã rời kho; đơn chỉ Hoàn thành sau khi đã thanh toán đủ và được duyệt nếu có yêu cầu duyệt.',
            'Ngày đặt hàng là ngày BC Bán hàng dùng để ghi nhận doanh thu.',
            'Nếu đơn cần duyệt, phải đủ điều kiện duyệt trước khi xuất kho.',
        ],
    },
    {
        'anchor': 'payments',
        'icon': 'fas fa-wallet',
        'title': 'Thanh toán và công nợ',
        'intro': 'Doanh thu, tiền đã thu và công nợ là ba số khác nhau; phải nhập đúng để tránh nhầm lãi với tiền mặt.',
        'path': 'Trong đơn hàng; Tài chính → Phiếu thu / Sổ quỹ',
        'steps': [
            'Khi khách trả tiền tại lúc bán, nhập số tiền và phương thức ngay trên đơn.',
            'Nếu khách trả nhiều phương thức, ghi từng dòng tiền mặt, chuyển khoản hoặc ví điện tử.',
            'Nếu khách còn nợ, lưu đúng số đã trả; hệ thống giữ phần còn lại là công nợ.',
            'Khi khách trả thêm sau đó, mở đúng đơn và tạo khoản thu bổ sung; không sửa doanh thu của đơn.',
            'Đối chiếu số Đã thu trên đơn với các phiếu thu và dòng tiền trong Sổ quỹ.',
            'Cuối ngày, lọc đơn còn nợ và xác nhận người chịu trách nhiệm nhắc thu.',
        ],
        'checks': [
            'Đơn còn nợ vẫn có doanh thu và lợi nhuận nếu đã ở trạng thái Đã xuất kho.',
            'Tiền khách trả thêm làm tăng Đã thu và giảm Công nợ, không làm tăng Doanh thu lần thứ hai.',
            'Không tạo hai phiếu thu cho cùng một lần chuyển tiền.',
            'Thu dư phải được kiểm tra; không dùng khoản thu dư của đơn này để tự bù nợ đơn khác.',
        ],
    },
    {
        'anchor': 'returns',
        'icon': 'fas fa-undo-alt',
        'title': 'Trả hàng và hoàn tiền',
        'intro': 'Phiếu trả hàng phải bám đơn gốc để cập nhật đúng số lượng, tiền hoàn, giá vốn hoàn và lịch sử khách.',
        'path': 'Bán hàng → Trả hàng',
        'steps': [
            'Tìm và mở đúng đơn gốc.',
            'Chọn sản phẩm, số lượng trả và lý do trả; không trả vượt số đã bán.',
            'Xác định hàng có nhập lại kho bán được hay cần xử lý riêng.',
            'Kiểm tra số tiền hoàn hoặc số tiền cấn trừ.',
            'Chọn phương thức hoàn tiền và đúng tài khoản/quỹ chi.',
            'Hoàn thành phiếu trả và kiểm tra lại tồn, sổ quỹ, công nợ và tab Trả hàng trên BC Bán hàng.',
        ],
        'checks': [
            'Ngày trả hàng là ngày báo cáo ghi nhận khoản hoàn trả.',
            'Phiếu trả Hủy không được tính vào báo cáo.',
            'Đơn hoàn đủ toàn bộ hàng không còn bị đánh dấu là đơn bán lỗ.',
            'Đơn hoàn một phần vẫn giữ dữ liệu bán và chỉ trừ phần đã trả.',
        ],
    },
    {
        'anchor': 'purchasing',
        'icon': 'fas fa-truck-loading',
        'title': 'Nhập hàng',
        'intro': 'Phiếu nhập làm tăng tồn và tạo lịch sử giá nhập; phải chọn đúng kho và ngày hàng thực nhận.',
        'path': 'Kho & Sản phẩm → Phiếu nhập',
        'steps': [
            'Chọn nhà cung cấp, kho nhận và ngày nhập.',
            'Tìm sản phẩm theo mã, tên, barcode hoặc quy cách rồi thêm vào phiếu.',
            'Nhập số lượng thực nhận và giá nhập thực tế trên từng dòng.',
            'Kiểm tra tổng tiền, ghi chú chênh lệch với đơn đặt hàng nếu có.',
            'Chỉ chuyển Hoàn thành khi đã nhận và kiểm hàng.',
            'Kiểm tra tồn kho và Lịch sử nhập của sản phẩm sau khi hoàn thành.',
        ],
        'checks': [
            'Phiếu Nháp dùng để chuẩn bị và chưa nên coi là hàng đã nhận.',
            'Không chọn nhầm kho nếu doanh nghiệp có nhiều điểm bán.',
            'Giá nhập sai có thể làm sai lịch sử mua và giá vốn tham khảo.',
            'BC Nhập hàng theo nhà cung cấp chỉ nên đối chiếu các phiếu Hoàn thành.',
        ],
    },
    {
        'anchor': 'inventory',
        'icon': 'fas fa-warehouse',
        'title': 'Quản lý kho và kiểm hàng',
        'intro': 'Tồn kho chỉ đáng tin khi mọi lần nhập, bán, trả, chuyển và kiểm hàng đều được ghi nhận.',
        'path': 'Kho & Sản phẩm → Quản lý kho / Kiểm hàng / Chuyển kho',
        'steps': [
            'Xem Tồn kho thực tế và Có thể bán tại từng kho.',
            'Dùng bộ lọc tồn âm, dưới tối thiểu hoặc trên tối đa để tìm hàng cần xử lý.',
            'Khi kiểm kê, đếm thực tế trước rồi nhập số thực đếm được.',
            'Đọc chênh lệch và ghi rõ nguyên nhân: thiếu nhập, thiếu xuất, hỏng, mất hoặc nhầm kho.',
            'Chỉ xác nhận phiếu kiểm sau khi quản lý duyệt chênh lệch.',
            'Khi chuyển kho, chọn rõ kho xuất, kho nhận và kiểm đếm ở cả hai đầu.',
            'Dùng Lịch sử kho và mã chứng từ để lần ngược thời điểm bắt đầu sai lệch.',
        ],
        'checks': [
            'Có thể bán có thể thấp hơn Tồn kho vì một phần hàng đang được giữ cho đơn chưa xuất.',
            'Không dùng phiếu kiểm để che lỗi quy trình; luôn ghi nguyên nhân.',
            'Tồn combo được tính từ thành phần và không chỉnh trực tiếp.',
            'Muốn lưu tồn âm, thương hiệu phải bật Cho phép tồn âm.',
        ],
    },
    {
        'anchor': 'finance',
        'icon': 'fas fa-cash-register',
        'title': 'Thu chi và sổ quỹ',
        'intro': 'Sổ quỹ phản ánh tiền vào ra; BC Bán hàng phản ánh hoạt động bán. Hai báo cáo trả lời hai câu hỏi khác nhau.',
        'path': 'Tài chính → Phiếu thu / Phiếu chi / Sổ quỹ',
        'steps': [
            'Tạo phiếu thu khi thực tế nhận tiền và phiếu chi khi thực tế chi tiền.',
            'Chọn đúng ngày, cửa hàng, quỹ, phương thức, đối tượng và chứng từ liên quan.',
            'Ghi nội dung đủ rõ để người khác biết khoản tiền phát sinh vì việc gì.',
            'Chỉ chứng từ Hoàn thành mới nên dùng để chốt quỹ.',
            'Cuối ngày đối chiếu riêng tiền mặt, ngân hàng và ví điện tử.',
            'Mở BC Tài chính để xem Tổng thu, Tổng phiếu chi, Tổng hàng nhập, Tổng chi và Lãi/Lỗ theo công thức quản trị.',
        ],
        'checks': [
            'Không dùng Doanh thu thay cho Tổng thu: đơn còn nợ có doanh thu nhưng chưa có đủ tiền thu.',
            'Không dùng Lợi nhuận gộp thay cho Lãi/Lỗ tài chính: hai chỉ tiêu có phạm vi chi phí khác nhau.',
            'Một khoản tiền chỉ được ghi một lần vào đúng quỹ.',
            'Phiếu nhập và phiếu chi mua hàng có thể cùng xuất hiện trong công thức quản trị của BC Tài chính; cần hiểu rõ trước khi kết luận.',
        ],
    },
]


RETAIL_FORMULA_GROUPS = [
    {
        'title': 'A. Đơn bán, thanh toán và công nợ',
        'items': [
            {
                'name': 'Thành tiền dòng hàng',
                'formula': 'Số lượng × Đơn giá − Chiết khấu dòng',
                'example': '2 × 100.000 − 20.000 = 180.000đ',
                'meaning': 'Giá trị của riêng một dòng sản phẩm.',
                'note': 'Chiết khấu dòng đã nằm trong Tiền hàng; không trừ lại lần nữa.',
            },
            {
                'name': 'Tiền hàng',
                'formula': 'Tổng Thành tiền của tất cả dòng',
                'example': '180.000 + 320.000 = 500.000đ',
                'meaning': 'Giá trị hàng trước chiết khấu chung và phí.',
                'note': 'Đây chưa phải số khách phải trả cuối cùng.',
            },
            {
                'name': 'Chiết khấu chung theo phần trăm',
                'formula': 'Tiền hàng × Tỷ lệ chiết khấu ÷ 100',
                'example': '500.000 × 10% = 50.000đ',
                'meaning': 'Khoản giảm thêm trên toàn đơn.',
                'note': 'Nếu nhập chiết khấu bằng tiền, hệ thống dùng trực tiếp số tiền đó.',
            },
            {
                'name': 'Tổng thanh toán / Doanh thu đơn',
                'formula': 'max(Tiền hàng − Chiết khấu chung + Phí vận chuyển + Chi phí khác, 0)',
                'example': '500.000 − 50.000 + 30.000 + 0 = 480.000đ',
                'meaning': 'Số tiền khách phải thanh toán và là doanh thu của đơn trước trả hàng.',
                'note': 'Không phụ thuộc khách đã trả đủ hay chưa.',
            },
            {
                'name': 'Còn phải thu trên đơn',
                'formula': 'max(Tổng thanh toán − Đã thu, 0)',
                'example': '480.000 − 200.000 = 280.000đ',
                'meaning': 'Số khách còn phải trả.',
                'note': 'Màn hình công nợ quy về 0 nếu đã thu đủ hoặc thu dư.',
            },
            {
                'name': 'Công nợ trên BC Bán hàng',
                'formula': 'Doanh thu − Đã thu',
                'example': '480.000 − 200.000 = 280.000đ',
                'meaning': 'Chênh lệch doanh thu và số đã thu trong phạm vi báo cáo.',
                'note': 'Nếu âm, dữ liệu đang có thu dư và cần kiểm tra.',
            },
            {
                'name': 'Tỷ lệ đã thu',
                'formula': 'Đã thu ÷ Doanh thu × 100%',
                'example': '200.000 ÷ 480.000 × 100% = 41,7%',
                'meaning': 'Tỷ lệ doanh thu đã chuyển thành tiền thu.',
                'note': 'Không tính khi doanh thu bằng 0.',
            },
            {
                'name': 'Giá trị đơn trung bình',
                'formula': 'Tổng doanh thu ÷ Số đơn',
                'example': '20.000.000 ÷ 100 đơn = 200.000đ/đơn',
                'meaning': 'Quy mô trung bình của một giao dịch.',
                'note': 'Chịu ảnh hưởng bởi phạm vi đơn và bộ lọc.',
            },
        ],
    },
    {
        'title': 'B. Giá vốn, trả hàng và lợi nhuận',
        'items': [
            {
                'name': 'Giá vốn dòng hàng',
                'formula': 'Số lượng bán × Giá vốn đơn vị',
                'example': '2 × 70.000 = 140.000đ',
                'meaning': 'Chi phí vốn của dòng hàng đã bán.',
                'note': 'Hệ thống ưu tiên giá vốn lưu tại thời điểm bán; thiếu dữ liệu mới dùng giá vốn/giá nhập hiện có.',
            },
            {
                'name': 'Lợi nhuận dòng',
                'formula': 'Doanh thu phân bổ cho dòng − Giá vốn dòng',
                'example': '180.000 − 140.000 = 40.000đ',
                'meaning': 'Lãi gộp của một dòng sản phẩm.',
                'note': 'Số âm là dòng bán lỗ.',
            },
            {
                'name': 'Lợi nhuận theo đơn',
                'formula': 'Doanh thu đơn − Tổng giá vốn của đơn',
                'example': '480.000 − 350.000 = 130.000đ',
                'meaning': 'Lãi gộp của đơn trước ảnh hưởng phiếu trả hàng.',
                'note': 'Không trừ lương, tiền thuê, điện nước hoặc chi phí vận hành.',
            },
            {
                'name': 'Doanh thu thuần',
                'formula': 'Doanh thu − Tiền hoàn trả',
                'example': '480.000 − 100.000 = 380.000đ',
                'meaning': 'Doanh thu còn lại sau trả hàng.',
                'note': 'Tiền trả được ghi theo Ngày trả hàng.',
            },
            {
                'name': 'Giá vốn hàng trả',
                'formula': 'Số lượng trả × Giá vốn đơn vị của đơn gốc',
                'example': '1 × 70.000 = 70.000đ',
                'meaning': 'Phần giá vốn được hoàn ngược khi hàng quay lại.',
                'note': 'Dữ liệu cũ thiếu giá vốn gốc có thể dùng giá vốn hiện có làm giá thay thế.',
            },
            {
                'name': 'Giá vốn thuần',
                'formula': 'Giá vốn bán − Giá vốn hàng trả',
                'example': '350.000 − 70.000 = 280.000đ',
                'meaning': 'Giá vốn còn lại sau trả hàng.',
                'note': 'Dùng để tính lợi nhuận gộp toàn kỳ.',
            },
            {
                'name': 'Lợi nhuận gộp toàn kỳ',
                'formula': 'Doanh thu thuần − Giá vốn thuần',
                'example': '380.000 − 280.000 = 100.000đ',
                'meaning': 'Lãi gộp sau ảnh hưởng hàng trả.',
                'note': 'Không phải Lãi/Lỗ trên BC Tài chính.',
            },
            {
                'name': 'Tỷ suất lợi nhuận gộp',
                'formula': 'Lợi nhuận gộp ÷ Doanh thu thuần × 100%',
                'example': '100.000 ÷ 380.000 × 100% = 26,3%',
                'meaning': 'Trong 100 đồng doanh thu thuần còn bao nhiêu đồng lãi gộp.',
                'note': 'Bằng 0 khi doanh thu thuần không dương.',
            },
            {
                'name': 'Tỷ lệ trả hàng',
                'formula': 'Tiền hoàn trả ÷ Doanh thu × 100%',
                'example': '100.000 ÷ 480.000 × 100% = 20,8%',
                'meaning': 'Mức độ doanh thu bị hoàn lại.',
                'note': 'Nên xem cùng lý do trả và sản phẩm bị trả.',
            },
        ],
    },
    {
        'title': 'C. Tồn kho và hàng bán chậm',
        'items': [
            {
                'name': 'Có thể bán',
                'formula': 'Tồn kho thực tế − Số lượng đang giữ cho đơn đủ điều kiện',
                'example': '100 − 15 = 85 sản phẩm',
                'meaning': 'Số lượng còn có thể nhận thêm đơn.',
                'note': 'Có thể bán thấp hơn tồn thực tế khi hàng đang chờ xử lý hoặc đóng gói.',
            },
            {
                'name': 'Chênh lệch kiểm hàng',
                'formula': 'Số lượng thực tế − Tồn hệ thống',
                'example': '97 − 100 = −3 sản phẩm',
                'meaning': 'Số cần điều chỉnh tăng hoặc giảm.',
                'note': 'Âm là thiếu, dương là thừa so với hệ thống.',
            },
            {
                'name': 'Tồn sau kiểm',
                'formula': 'Tồn hệ thống + Chênh lệch = Số lượng thực tế',
                'example': '100 + (−3) = 97 sản phẩm',
                'meaning': 'Tồn mới sau khi xác nhận kiểm hàng.',
                'note': 'Phải ghi nguyên nhân chênh lệch.',
            },
            {
                'name': 'Cần nhập tối thiểu',
                'formula': 'max(Tồn tối thiểu − Tồn hiện tại, 0)',
                'example': '50 − 32 = 18 sản phẩm',
                'meaning': 'Số lượng cần bổ sung để đạt ngưỡng tối thiểu.',
                'note': 'Chỉ có ý nghĩa khi khai báo đúng tồn tối thiểu.',
            },
            {
                'name': 'Giá trị tồn trên BC Kho',
                'formula': 'max(Tồn hiện tại, 0) × Giá vốn',
                'example': '32 × 70.000 = 2.240.000đ',
                'meaning': 'Giá trị vốn ước tính của hàng còn tồn dương.',
                'note': 'Tồn âm hiển thị để xử lý nhưng không làm giảm giá trị tồn dương.',
            },
            {
                'name': 'Ngày chưa bán',
                'formula': 'Ngày hiện tại − Ngày bán gần nhất',
                'example': '25/07 − 10/06 = 45 ngày',
                'meaning': 'Thời gian sản phẩm không phát sinh bán thực tế.',
                'note': 'Sản phẩm chưa từng bán được hiển thị riêng.',
            },
            {
                'name': 'Giá trị tồn chậm',
                'formula': 'Tồn hiện tại × Giá tính tồn',
                'example': '20 × 70.000 = 1.400.000đ',
                'meaning': 'Số vốn đang nằm ở mặt hàng bán chậm.',
                'note': 'Giá tính tồn ưu tiên giá vốn, sau đó giá nhập.',
            },
            {
                'name': 'Có thể bán của combo',
                'formula': 'Giá trị nhỏ nhất của phần nguyên: Có thể bán thành phần ÷ SL thành phần cần cho 1 combo',
                'example': 'Thành phần A đủ 10 combo, B đủ 7 combo → combo có thể bán = 7',
                'meaning': 'Số combo tối đa có thể tạo từ các thành phần đang có.',
                'note': 'Combo được tính tự động và không chỉnh tồn trực tiếp.',
            },
        ],
    },
    {
        'title': 'D. Thu chi và BC Tài chính',
        'items': [
            {
                'name': 'Tổng thu',
                'formula': 'Tổng số tiền phiếu thu Hoàn thành trong kỳ',
                'example': 'Tiền mặt 6 triệu + Chuyển khoản 4 triệu = 10 triệu',
                'meaning': 'Dòng tiền đã thu theo chứng từ.',
                'note': 'Không bằng Doanh thu nếu có công nợ hoặc thu tiền khác ngày bán.',
            },
            {
                'name': 'Tổng phiếu chi',
                'formula': 'Tổng số tiền phiếu chi Hoàn thành trong kỳ',
                'example': 'Chi vận chuyển 1 triệu + chi vận hành 2 triệu = 3 triệu',
                'meaning': 'Dòng tiền chi theo phiếu chi.',
                'note': 'Lọc theo Ngày chi.',
            },
            {
                'name': 'Tổng hàng nhập',
                'formula': 'Tổng tiền phiếu nhập Hoàn thành trong kỳ',
                'example': 'Phiếu nhập 1: 5 triệu + phiếu nhập 2: 7 triệu = 12 triệu',
                'meaning': 'Giá trị hàng nhập theo chứng từ kho.',
                'note': 'Lọc theo Ngày nhập và kho thuộc cửa hàng.',
            },
            {
                'name': 'Tổng chi trên BC Tài chính',
                'formula': 'Tổng phiếu chi + Tổng hàng nhập',
                'example': '3 triệu + 12 triệu = 15 triệu',
                'meaning': 'Tổng chi theo công thức quản trị hiện tại.',
                'note': 'Nếu một lần mua hàng vừa có phiếu nhập vừa có phiếu chi, cả hai có thể cùng được cộng.',
            },
            {
                'name': 'Lãi/Lỗ trên BC Tài chính',
                'formula': 'Tổng thu − Tổng chi',
                'example': '20 triệu − 15 triệu = 5 triệu',
                'meaning': 'Chênh lệch thu chi theo công thức quản trị.',
                'note': 'Không phải Lợi nhuận gộp bán hàng.',
            },
            {
                'name': 'Số dư quỹ cuối kỳ',
                'formula': 'Số dư đầu kỳ + Thu trong kỳ − Chi trong kỳ',
                'example': '5 triệu + 20 triệu − 15 triệu = 10 triệu',
                'meaning': 'Số dư lý thuyết của một quỹ sau phát sinh.',
                'note': 'Phải đối chiếu với tiền hoặc số dư tài khoản thực tế.',
            },
        ],
    },
]


RETAIL_SALES_REPORT_SCOPE = [
    {
        'name': 'Từ ngày – Đến ngày',
        'detail': 'Đơn bán lọc theo Ngày đặt hàng; phiếu trả lọc theo Ngày trả hàng. Hai ngày đầu và cuối đều được tính.',
    },
    {
        'name': 'Đã xuất kho + Hoàn thành',
        'detail': 'Phạm vi mặc định để đọc doanh thu đã thực hiện.',
    },
    {
        'name': 'Tất cả đơn chưa hủy',
        'detail': 'Dùng để kiểm tra vận hành; gồm cả đơn chưa xuất kho nên không nên coi toàn bộ là doanh thu đã thực hiện.',
    },
    {
        'name': 'Bộ lọc cửa hàng, khách, sản phẩm, nhân viên',
        'detail': 'Mọi số tổng và bảng chi tiết thay đổi theo bộ lọc. Khi lọc sản phẩm, doanh thu, phí và đã thu được phân bổ cho phần hàng đang xem.',
    },
    {
        'name': 'Xem theo ngày / tháng / năm',
        'detail': 'Chỉ thay đổi cách gom nhóm thời gian, không thay đổi tổng dữ liệu cùng phạm vi.',
    },
    {
        'name': 'Riêng tab Hàng bán chậm',
        'detail': 'Dùng toàn bộ lịch sử bán của đơn Đã xuất kho/Hoàn thành và chỉ lấy sản phẩm còn tồn; không bị giới hạn bởi khoảng ngày báo cáo.',
    },
]


RETAIL_SALES_REPORT_TABLES = [
    {
        'title': '1. Thẻ Tổng quan',
        'purpose': 'Đọc nhanh kết quả của toàn bộ phạm vi đang lọc.',
        'columns': [
            {'name': 'Đơn hàng', 'formula': 'Đếm đơn thỏa bộ lọc', 'meaning': 'Số giao dịch được đưa vào báo cáo.'},
            {'name': 'Doanh thu', 'formula': 'Tổng doanh thu các đơn', 'meaning': 'Giá trị bán trước khi trừ hàng trả; không phụ thuộc đã thu đủ.'},
            {'name': 'Lợi nhuận gộp', 'formula': 'Doanh thu thuần − Giá vốn thuần', 'meaning': 'Lãi gộp sau trả hàng, chưa trừ chi phí vận hành.'},
            {'name': 'Công nợ', 'formula': 'Tổng (Doanh thu − Đã thu)', 'meaning': 'Chênh lệch tiền phải thu và đã thu trong báo cáo.'},
            {'name': 'Nhập hàng', 'formula': 'Tổng tiền phiếu nhập chưa hủy trong kỳ', 'meaning': 'Giá trị nhập tham khảo; không trừ trực tiếp vào lợi nhuận gộp.'},
            {'name': 'Giá vốn thuần', 'formula': 'Giá vốn bán − Giá vốn hàng trả', 'meaning': 'Chi phí hàng đã bán còn lại sau hoàn ngược.'},
            {'name': 'Trả hàng', 'formula': 'Tổng tiền hoàn trả', 'meaning': 'Giá trị làm giảm doanh thu thuần.'},
            {'name': 'Đã thu', 'formula': 'Doanh thu − Công nợ', 'meaning': 'Số tiền đã ghi nhận thanh toán trên các đơn.'},
            {'name': 'Đơn báo lỗ', 'formula': 'Đếm đơn có Doanh thu − Giá vốn < 0', 'meaning': 'Đơn lỗ trước chi phí vận hành; loại đơn đã hoàn đủ.'},
        ],
    },
    {
        'title': '2. Bảng Doanh thu theo ngày và Tổng hợp ngày',
        'purpose': 'Biết ngày nào tạo doanh thu, trả hàng và lợi nhuận.',
        'columns': [
            {'name': 'Ngày / Tháng / Năm', 'formula': 'Gom theo Ngày đặt hàng', 'meaning': 'Mốc thời gian của doanh thu.'},
            {'name': 'Số ĐH', 'formula': 'Đếm đơn trong mốc thời gian', 'meaning': 'Số giao dịch bán.'},
            {'name': 'Tiền hàng', 'formula': 'Tổng thành tiền dòng hàng', 'meaning': 'Giá trị trước chiết khấu chung và phí.'},
            {'name': 'Doanh thu', 'formula': 'Tổng doanh thu đơn', 'meaning': 'Doanh thu trước hàng trả.'},
            {'name': 'Trả hàng', 'formula': 'Tổng hoàn trả theo Ngày trả', 'meaning': 'Khoản giảm doanh thu trong ngày trả.'},
            {'name': 'Doanh thu thuần', 'formula': 'Doanh thu − Trả hàng', 'meaning': 'Doanh thu sau trả hàng.'},
            {'name': 'Giá vốn thuần', 'formula': 'Giá vốn bán − Giá vốn trả', 'meaning': 'Chi phí vốn còn lại.'},
            {'name': 'Lợi nhuận gộp', 'formula': 'Doanh thu thuần − Giá vốn thuần', 'meaning': 'Lãi gộp sau trả hàng.'},
            {'name': 'Tỷ suất LN gộp', 'formula': 'LN gộp ÷ Doanh thu thuần × 100%', 'meaning': 'Hiệu quả lãi của ngày.'},
            {'name': 'Lợi nhuận ròng', 'formula': 'Hiện bằng Lợi nhuận gộp', 'meaning': 'Chưa trừ chi phí vận hành; xem BC Tài chính để đọc thu chi.'},
        ],
    },
    {
        'title': '3. DT Mặt hàng, Chi tiết SKU và Danh mục',
        'purpose': 'Biết bán mặt hàng nào, tạo doanh thu và lãi bao nhiêu.',
        'columns': [
            {'name': 'Sản phẩm / SKU / Danh mục / Loại SP', 'formula': 'Thông tin danh mục', 'meaning': 'Nhận diện và gom nhóm hàng.'},
            {'name': 'Ngày / Khách / Mã đơn / Nhân viên', 'formula': 'Thông tin đơn gốc', 'meaning': 'Truy ngược dòng SKU về giao dịch.'},
            {'name': 'SL bán', 'formula': 'Tổng số lượng dòng đơn', 'meaning': 'Số lượng bán trước khi trừ hàng trả trong bảng thông thường.'},
            {'name': 'Doanh thu dòng', 'formula': 'Doanh thu đơn phân bổ theo tỷ trọng dòng', 'meaning': 'Doanh thu của riêng sản phẩm sau chiết khấu và phí.'},
            {'name': 'Giá vốn / Tiền vốn', 'formula': 'SL × Giá vốn đơn vị', 'meaning': 'Chi phí vốn của sản phẩm.'},
            {'name': 'LN dòng / LN gộp', 'formula': 'Doanh thu dòng − Giá vốn', 'meaning': 'Lãi của sản phẩm; âm là bán lỗ.'},
            {'name': 'Biên LN', 'formula': 'Lợi nhuận ÷ Doanh thu × 100%', 'meaning': 'Tỷ lệ lãi của mặt hàng hoặc nhóm.'},
            {'name': 'Tỷ trọng', 'formula': 'Doanh thu nhóm ÷ Tổng doanh thu nhóm × 100%', 'meaning': 'Mức đóng góp trong bảng.'},
        ],
    },
    {
        'title': '4. Nhà cung cấp',
        'purpose': 'Đánh giá hàng của nhà cung cấp nào đang tiêu thụ và tạo lợi nhuận tốt.',
        'columns': [
            {'name': 'Nhà cung cấp', 'formula': 'NCC gắn trên sản phẩm', 'meaning': 'Nguồn cung của nhóm hàng.'},
            {'name': 'Mặt hàng', 'formula': 'Đếm sản phẩm khác nhau', 'meaning': 'Số mã có phát sinh.'},
            {'name': 'Số ĐH', 'formula': 'Đếm đơn khác nhau', 'meaning': 'Số đơn có hàng của NCC.'},
            {'name': 'SL bán', 'formula': 'Tổng số lượng bán', 'meaning': 'Lượng bán trước trả.'},
            {'name': 'SL trả', 'formula': 'Tổng số lượng trả', 'meaning': 'Lượng khách trả lại.'},
            {'name': 'Tiêu thụ ròng', 'formula': 'SL bán − SL trả', 'meaning': 'Lượng thực tiêu thụ.'},
            {'name': 'Doanh thu thuần', 'formula': 'Doanh thu hàng NCC − Hoàn trả', 'meaning': 'Doanh thu còn lại.'},
            {'name': 'Giá vốn thuần', 'formula': 'Giá vốn bán − Giá vốn trả', 'meaning': 'Chi phí vốn còn lại.'},
            {'name': 'Lợi nhuận', 'formula': 'Doanh thu thuần − Giá vốn thuần', 'meaning': 'Lãi gộp từ hàng của NCC.'},
            {'name': 'Tỷ trọng DT', 'formula': 'DT thuần NCC ÷ Tổng DT thuần NCC × 100%', 'meaning': 'Mức đóng góp của NCC.'},
            {'name': 'Mặt hàng bán chạy', 'formula': 'Xếp theo tiêu thụ ròng rồi doanh thu', 'meaning': 'Ba mặt hàng nổi bật của NCC.'},
        ],
    },
    {
        'title': '5. Khách hàng, nhân viên và cửa hàng',
        'purpose': 'Biết ai mua, ai bán và điểm bán nào tạo kết quả.',
        'columns': [
            {'name': 'Khách / Nhóm / Buôn-lẻ', 'formula': 'Thông tin hồ sơ khách', 'meaning': 'Đối tượng được gom doanh thu.'},
            {'name': 'Nhân viên', 'formula': 'NV bán hàng trên đơn', 'meaning': 'Người được ghi nhận phụ trách.'},
            {'name': 'Cửa hàng', 'formula': 'Cửa hàng trên đơn', 'meaning': 'Điểm bán phát sinh.'},
            {'name': 'Số ĐH', 'formula': 'Đếm đơn trong nhóm', 'meaning': 'Khối lượng giao dịch.'},
            {'name': 'Doanh thu', 'formula': 'Tổng doanh thu đơn trong nhóm', 'meaning': 'Giá trị bán trước trả hàng.'},
            {'name': 'Giá vốn', 'formula': 'Tổng giá vốn đơn trong nhóm', 'meaning': 'Chi phí hàng bán.'},
            {'name': 'Lợi nhuận', 'formula': 'Doanh thu − Giá vốn', 'meaning': 'Lãi theo đơn trước trả hàng.'},
            {'name': 'Đã thu', 'formula': 'Tổng số đã thanh toán', 'meaning': 'Tiền đã thu của nhóm.'},
            {'name': 'Công nợ', 'formula': 'Doanh thu − Đã thu', 'meaning': 'Phần còn phải thu.'},
            {'name': 'Trả hàng', 'formula': 'Tổng hoàn trả gắn với nhân viên', 'meaning': 'Giá trị hàng bị trả.'},
            {'name': 'Tỷ lệ / Tỷ trọng', 'formula': 'Doanh thu nhóm ÷ Tổng doanh thu × 100%', 'meaning': 'Mức đóng góp doanh thu.'},
        ],
    },
    {
        'title': '6. Theo đơn hàng',
        'purpose': 'Đối chiếu trực tiếp từng đơn và tìm nguyên nhân lỗ hoặc nợ.',
        'columns': [
            {'name': 'Mã ĐH', 'formula': 'Mã chứng từ', 'meaning': 'Bấm để mở đơn gốc.'},
            {'name': 'Ngày', 'formula': 'Ngày đặt hàng', 'meaning': 'Ngày ghi nhận doanh thu.'},
            {'name': 'Khách / Buôn-lẻ / NV / Cửa hàng', 'formula': 'Thông tin trên đơn', 'meaning': 'Đối tượng và điểm bán.'},
            {'name': 'Sản phẩm lỗ', 'formula': 'Dòng có Doanh thu dòng − Giá vốn dòng < 0', 'meaning': 'Mặt hàng làm đơn bị lỗ.'},
            {'name': 'Tiền hàng', 'formula': 'Tổng thành tiền dòng', 'meaning': 'Trước chiết khấu chung và phí.'},
            {'name': 'Chiết khấu', 'formula': 'Chiết khấu chung của đơn', 'meaning': 'Khoản giảm toàn đơn.'},
            {'name': 'Phí vận chuyển', 'formula': 'Phí trên đơn', 'meaning': 'Khoản cộng vào doanh thu.'},
            {'name': 'Chi phí khác', 'formula': 'Phí khác trên đơn', 'meaning': 'Khoản cộng thêm.'},
            {'name': 'Doanh thu', 'formula': 'Tiền hàng − CK + Phí VC + Chi phí khác', 'meaning': 'Số khách phải thanh toán.'},
            {'name': 'Đã thu', 'formula': 'Số đã thanh toán trên đơn', 'meaning': 'Tiền đã ghi nhận thu.'},
            {'name': 'Công nợ', 'formula': 'Doanh thu − Đã thu', 'meaning': 'Phần còn thiếu; đơn nợ vẫn có doanh thu và lợi nhuận.'},
            {'name': 'Giá vốn', 'formula': 'Tổng giá vốn dòng', 'meaning': 'Chi phí vốn của đơn.'},
            {'name': 'Lợi nhuận', 'formula': 'Doanh thu − Giá vốn', 'meaning': 'Lãi gộp đơn trước trả hàng và chi phí vận hành.'},
            {'name': 'TT đơn', 'formula': 'Trạng thái xử lý lưu trên đơn', 'meaning': 'Tiến độ thực hiện hàng.'},
            {'name': 'TT thanh toán', 'formula': 'Trạng thái thanh toán lưu trên đơn', 'meaning': 'Chưa, một phần hoặc đã thanh toán.'},
        ],
    },
    {
        'title': '7. Trả hàng và Lợi nhuận gộp',
        'purpose': 'Biết giá trị bị hoàn và ảnh hưởng thật tới doanh thu, giá vốn, lợi nhuận.',
        'columns': [
            {'name': 'Mã phiếu / Đơn gốc', 'formula': 'Mã chứng từ liên quan', 'meaning': 'Truy ngược nghiệp vụ trả.'},
            {'name': 'Ngày', 'formula': 'Ngày trả hàng', 'meaning': 'Ngày ghi nhận khoản hoàn.'},
            {'name': 'Khách / Nhân viên', 'formula': 'Thông tin phiếu và đơn', 'meaning': 'Đối tượng liên quan.'},
            {'name': 'SL trả', 'formula': 'Tổng số lượng trả', 'meaning': 'Lượng hàng quay lại.'},
            {'name': 'Hoàn tiền', 'formula': 'Tổng giá trị trả', 'meaning': 'Khoản giảm doanh thu thuần.'},
            {'name': 'Giá vốn hoàn', 'formula': 'SL trả × Giá vốn gốc', 'meaning': 'Khoản giảm giá vốn bán.'},
            {'name': 'Số phiếu', 'formula': 'Đếm phiếu có sản phẩm', 'meaning': 'Tần suất sản phẩm bị trả.'},
            {'name': 'Doanh thu thuần', 'formula': 'Doanh thu − Hoàn tiền', 'meaning': 'Doanh thu còn lại.'},
            {'name': 'Giá vốn thuần', 'formula': 'Giá vốn bán − Giá vốn hoàn', 'meaning': 'Chi phí vốn còn lại.'},
            {'name': 'Lợi nhuận gộp', 'formula': 'DT thuần − GV thuần', 'meaning': 'Lãi sau trả hàng.'},
            {'name': 'Biên LN', 'formula': 'LN gộp ÷ DT thuần × 100%', 'meaning': 'Tỷ lệ lãi sau trả.'},
        ],
    },
    {
        'title': '8. Hàng bán chậm',
        'purpose': 'Tìm hàng còn tồn lâu để nhập ít lại, điều chuyển hoặc xả hàng.',
        'columns': [
            {'name': 'Sản phẩm / Danh mục / NCC', 'formula': 'Thông tin danh mục', 'meaning': 'Nhận diện hàng còn tồn.'},
            {'name': 'Lần bán gần nhất', 'formula': 'Ngày bán mới nhất của đơn đã xuất/hoàn thành', 'meaning': 'Mốc bán thực tế gần nhất.'},
            {'name': 'Ngày chưa bán', 'formula': 'Hôm nay − Lần bán gần nhất', 'meaning': 'Thời gian không phát sinh bán.'},
            {'name': 'Tồn hiện tại', 'formula': 'Tổng tồn trong phạm vi', 'meaning': 'Lượng hàng đang còn.'},
            {'name': 'Giá tính tồn', 'formula': 'Ưu tiên Giá vốn, sau đó Giá nhập', 'meaning': 'Đơn giá ước tính vốn.'},
            {'name': 'Giá trị tồn', 'formula': 'Tồn × Giá tính tồn', 'meaning': 'Số vốn nằm ở hàng chậm.'},
        ],
    },
]


RETAIL_REPORT_EXAMPLES = [
    {
        'title': 'Đơn đã trả đủ',
        'input': 'Doanh thu 1.000.000đ; giá vốn 700.000đ; đã thu 1.000.000đ.',
        'output': 'Công nợ 0đ; lợi nhuận theo đơn 300.000đ.',
        'explain': 'Doanh thu và tiền thu bằng nhau vì khách đã trả đủ.',
    },
    {
        'title': 'Đơn đã xuất kho nhưng còn nợ',
        'input': 'Doanh thu 1.000.000đ; giá vốn 700.000đ; đã thu 400.000đ.',
        'output': 'Công nợ 600.000đ; lợi nhuận theo đơn vẫn 300.000đ.',
        'explain': 'Đơn Đã xuất kho được ghi nhận doanh thu và lợi nhuận; đơn giữ trạng thái này cho đến khi thu đủ tiền.',
    },
    {
        'title': 'Đơn có chiết khấu và phí',
        'input': 'Tiền hàng 1.000.000đ; chiết khấu 100.000đ; phí vận chuyển 30.000đ; giá vốn 700.000đ.',
        'output': 'Doanh thu 930.000đ; lợi nhuận theo đơn 230.000đ.',
        'explain': 'Doanh thu = 1.000.000 − 100.000 + 30.000.',
    },
    {
        'title': 'Khách trả một phần hàng',
        'input': 'Doanh thu 1.000.000đ; giá vốn bán 700.000đ; hoàn tiền 200.000đ; giá vốn hàng trả 140.000đ.',
        'output': 'Doanh thu thuần 800.000đ; giá vốn thuần 560.000đ; lợi nhuận gộp 240.000đ.',
        'explain': 'Trả hàng làm giảm cả doanh thu và giá vốn tương ứng.',
    },
]


RETAIL_DAILY_CHECKLIST = [
    {
        'time': 'Đầu ngày',
        'items': [
            'Đăng nhập đúng tài khoản và cửa hàng.',
            'Kiểm tra đơn chưa xử lý, đơn đang giữ hàng và lịch giao.',
            'Xem hàng dưới tồn tối thiểu, tồn âm hoặc cần nhập.',
            'Kiểm tra quỹ tiền mặt đầu ngày nếu cửa hàng chốt ca.',
        ],
    },
    {
        'time': 'Trong ngày',
        'items': [
            'Mỗi đơn nhập đúng khách, kho, sản phẩm, giá, chiết khấu và số đã thu.',
            'Ghi nhận ngay phiếu thu, chi, nhập, trả hoặc chuyển kho khi nghiệp vụ phát sinh.',
            'Không để dồn chứng từ sang ngày khác nếu muốn báo cáo theo ngày chính xác.',
            'Xử lý cảnh báo lỗ, âm kho hoặc đơn cần duyệt trước khi giao hàng.',
        ],
    },
    {
        'time': 'Cuối ngày',
        'items': [
            'Đếm số đơn Đã xuất kho/Hoàn thành và đối chiếu BC Bán hàng.',
            'Đối chiếu Đã thu theo tiền mặt, ngân hàng, ví với Sổ quỹ và số thực tế.',
            'Lập danh sách đơn còn nợ và khoản cần thu tiếp.',
            'Kiểm tra đơn trả, phiếu chi và hàng nhập trong ngày.',
            'Ghi nhận chênh lệch trước khi chốt ca; không sửa số chỉ để làm báo cáo khớp.',
        ],
    },
]


RETAIL_TROUBLESHOOTING = [
    {
        'problem': 'Doanh thu lớn hơn tiền đã thu',
        'cause': 'Có đơn chưa thanh toán đủ hoặc khách trả sau ngày bán.',
        'check': 'Mở tab Theo đơn, so sánh Doanh thu, Đã thu và Công nợ; sau đó đối chiếu phiếu thu.',
    },
    {
        'problem': 'Đơn đã xuất kho vẫn có công nợ',
        'cause': 'Hàng đã rời kho nhưng khách chưa thanh toán đủ.',
        'check': 'Kiểm tra Tổng thanh toán, Đã thu và lịch sử phiếu thu; thu đủ tiền để đơn chuyển Hoàn thành.',
    },
    {
        'problem': 'Lợi nhuận quá cao hoặc quá thấp',
        'cause': 'Giá vốn thiếu/sai, chiết khấu hoặc phí sai, hoặc phiếu trả chưa đúng.',
        'check': 'Mở tab Theo đơn và Chi tiết SKU; kiểm tra Doanh thu dòng, Tiền vốn và sản phẩm lỗ.',
    },
    {
        'problem': 'BC Bán hàng khác BC Tài chính',
        'cause': 'BC Bán hàng tính doanh thu và lợi nhuận gộp; BC Tài chính tính thu, chi và hàng nhập.',
        'check': 'So sánh đúng công thức và cùng khoảng ngày; không so trực tiếp hai chỉ tiêu khác bản chất.',
    },
    {
        'problem': 'Tồn kho khác số đếm thực tế',
        'cause': 'Thiếu phiếu nhập, bán, trả, chuyển kho; chọn nhầm kho; hoặc có điều chỉnh chưa ghi nhận.',
        'check': 'Mở Lịch sử kho, lần theo thời gian và mã chứng từ; sau đó kiểm hàng có ghi nguyên nhân.',
    },
    {
        'problem': 'Có thể bán thấp hơn Tồn kho',
        'cause': 'Một phần hàng đang được giữ cho đơn chưa xuất kho.',
        'check': 'Kiểm tra các đơn ở trạng thái Đơn hàng, Đang xử lý hoặc Đang đóng gói.',
    },
    {
        'problem': 'Báo cáo thiếu đơn',
        'cause': 'Sai khoảng ngày, cửa hàng, phạm vi đơn hoặc bộ lọc.',
        'check': 'Xóa bộ lọc, kiểm tra Ngày đặt hàng và thử phạm vi Tất cả đơn chưa hủy.',
    },
    {
        'problem': 'Công nợ âm trên BC Bán hàng',
        'cause': 'Số Đã thu lớn hơn Doanh thu của đơn hoặc dữ liệu lọc/phân bổ đang có thu dư.',
        'check': 'Mở từng đơn âm, kiểm tra phiếu thu trùng, thu dư và lịch sử chỉnh thanh toán.',
    },
    {
        'problem': 'Phiếu hoàn không ghi nhận tiền chi',
        'cause': 'Phương thức hoàn chưa có quỹ mặc định hoặc người dùng chưa chọn quỹ.',
        'check': 'Vào Cài đặt → Phương thức TT để gắn quỹ, rồi kiểm tra lại phiếu trả.',
    },
]


RETAIL_FAQS = [
    {
        'question': '1) Đơn hàng đã Hoàn thành thì trong kho đã xuất hay chưa xuất?',
        'short_answer': 'Đã xuất kho và tồn kho đã được trừ trước đó.',
        'answer': [
            (
                'Theo quy trình chuẩn, đơn phải đi qua trạng thái Đã xuất kho trước khi chuyển sang Hoàn thành. '
                'Hệ thống trừ tồn ngay tại bước Đã xuất kho.'
            ),
            (
                'Khi đơn chuyển từ Đã xuất kho sang Hoàn thành, hệ thống chỉ đổi trạng thái nghiệp vụ và không trừ kho lần thứ hai.'
            ),
            (
                'Sản phẩm hàng hóa bị trừ khỏi kho xuất ghi trên đơn. Sản phẩm dịch vụ không trừ kho; '
                'nếu bán combo, hệ thống trừ tồn các sản phẩm thành phần.'
            ),
        ],
        'checks': [
            'Mở đơn và kiểm tra trạng thái Hoàn thành cùng Kho xuất đã chọn.',
            'Vào DS Sản phẩm → Lịch sử kho của sản phẩm để tìm dòng Xuất kho có mã chứng từ là mã đơn hàng.',
            'Đối chiếu số lượng xuất với số lượng sản phẩm trên đơn.',
        ],
        'exception': (
            'Nếu đơn đã Hoàn thành nhưng không có lịch sử xuất kho hoặc tồn chưa giảm, đây là dữ liệu bất thường '
            'do dữ liệu cũ, sửa trực tiếp cơ sở dữ liệu hoặc sự cố khi xử lý. Không tự trừ kho thêm vì có thể trừ hai lần; '
            'hãy báo quản lý hoặc bộ phận hỗ trợ để đối chiếu và đồng bộ.'
        ),
    },
    {
        'question': '2) Đơn hàng đang ở trạng thái Đã xuất kho, để đơn Hoàn thành cần thêm bước nào?',
        'short_answer': 'Cần thu đủ tiền và duyệt đơn nếu đơn có yêu cầu người duyệt.',
        'answer': [
            (
                'Đơn Đã xuất kho được chuyển sang Hoàn thành khi đồng thời thỏa hai điều kiện: '
                'trạng thái thanh toán là Đã thanh toán và đơn đã được duyệt nếu có chỉ định người duyệt.'
            ),
            (
                'Điều kiện thanh toán đủ được xác định theo công thức: Tổng các phiếu thu Hoàn thành '
                'của đơn ≥ Tổng thanh toán của đơn. Phiếu thu Nháp hoặc đã Hủy không được tính.'
            ),
            (
                'Với đơn còn nợ, mở đơn và dùng chức năng Thu tiền để ghi nhận phần khách trả thêm. '
                'Khi thu đủ và đủ điều kiện duyệt, hệ thống tự chuyển đơn sang Hoàn thành. '
                'Nếu đơn đã đủ điều kiện nhưng chưa tự chuyển, mở đơn và chọn bước Hoàn thành.'
            ),
            (
                'Bước Hoàn thành chỉ chốt quy trình đơn hàng; hệ thống không trừ tồn kho lần thứ hai.'
            ),
        ],
        'checks': [
            'So sánh Tổng thanh toán với Đã thu và số Còn phải thu trên đơn.',
            'Mở lịch sử thanh toán, kiểm tra các phiếu thu đúng đơn và đang ở trạng thái Hoàn thành.',
            'Nếu đơn có người duyệt, kiểm tra trạng thái duyệt phải là Đã duyệt.',
            'Sau khi thu đủ hoặc duyệt đơn, tải lại đơn để kiểm tra trạng thái Hoàn thành.',
        ],
        'exception': (
            'Nếu đã thu đủ và đã duyệt nhưng đơn vẫn ở Đã xuất kho, không tạo thêm phiếu thu. '
            'Hãy kiểm tra phiếu thu có bị ghi nhầm sang đơn khác, đang ở trạng thái Nháp/Hủy hoặc đã bị xóa; '
            'sau đó báo quản lý hay bộ phận hỗ trợ nếu số liệu vẫn không đồng bộ.'
        ),
    },
    {
        'question': '3) Đơn hàng chỉ đang ở trạng thái Đã xuất kho có được tính doanh thu không?',
        'short_answer': 'Có. Báo cáo bán hàng mặc định tính doanh thu của cả đơn Đã xuất kho và Hoàn thành.',
        'answer': [
            (
                'Phạm vi mặc định của Báo cáo bán hàng là Đã xuất kho + Hoàn thành. Vì vậy, đơn Đã xuất kho '
                'được xem là giao dịch bán đã thực hiện và được đưa vào doanh thu nếu thỏa khoảng ngày, cửa hàng '
                'và các bộ lọc đang chọn.'
            ),
            (
                'Doanh thu đơn = max(Tiền hàng − Chiết khấu chung + Phí vận chuyển + Chi phí khác, 0). '
                'Doanh thu được ghi theo Ngày đặt hàng, không theo ngày xuất kho hoặc ngày khách thanh toán.'
            ),
            (
                'Khách chưa trả đủ vẫn ghi nhận toàn bộ doanh thu của đơn. Số đã trả được ghi vào Đã thu; '
                'phần còn lại được ghi vào Công nợ theo công thức: Công nợ = Doanh thu − Đã thu.'
            ),
            (
                'Đơn Đã xuất kho cũng được tính giá vốn và lợi nhuận gộp. Khi khách trả thêm sau đó, '
                'khoản thu chỉ làm tăng Đã thu và giảm Công nợ, không làm tăng doanh thu lần thứ hai.'
            ),
        ],
        'checks': [
            'Trong BC Bán hàng, chọn Phạm vi đơn là Đã xuất kho + Hoàn thành.',
            'Chọn khoảng ngày có chứa Ngày đặt hàng của đơn và đúng cửa hàng.',
            'Mở tab Theo đơn hàng, tìm mã đơn rồi đối chiếu Doanh thu, Đã thu và Công nợ.',
            'Nếu có trả hàng, kiểm tra thêm Trả hàng và Doanh thu thuần vì tiền hoàn làm giảm doanh thu thuần.',
        ],
        'exception': (
            'Không dùng Tổng thu trên BC Tài chính để kết luận đơn có doanh thu hay chưa. '
            'BC Bán hàng ghi nhận giá trị bán; BC Tài chính ghi nhận dòng tiền thực thu, nên hai số có thể khác nhau '
            'khi khách còn nợ hoặc thanh toán vào ngày khác.'
        ),
    },
]
