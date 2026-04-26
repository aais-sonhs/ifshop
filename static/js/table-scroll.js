(function () {
    'use strict';

    var TABLE_SCROLL_SELECTOR = '.table-responsive';
    var ACTIVE_CLASS = 'table-scroll-active';
    var BOTTOM_MARGIN = 10;
    var MIN_TABLE_HEIGHT = 300;
    var activeContainer = null;

    function isElement(node) {
        return node && node.nodeType === 1;
    }

    function getClosestContainer(target) {
        return isElement(target) ? target.closest(TABLE_SCROLL_SELECTOR) : null;
    }

    function isScrollable(container) {
        if (!container) {
            return false;
        }

        return container.scrollWidth > container.clientWidth + 1 ||
            container.scrollHeight > container.clientHeight + 1;
    }

    function primeContainer(container) {
        if (!container || container.hasAttribute('tabindex')) {
            return container;
        }

        container.setAttribute('tabindex', '0');
        return container;
    }

    function setActiveContainer(container) {
        if (activeContainer && activeContainer !== container) {
            activeContainer.classList.remove(ACTIVE_CLASS);
        }

        activeContainer = container && isScrollable(container) ? container : null;

        if (activeContainer) {
            activeContainer.classList.add(ACTIVE_CLASS);
        }
    }

    function normalizeDelta(delta, deltaMode, pageSize) {
        if (deltaMode === 1) {
            return delta * 16;
        }

        if (deltaMode === 2) {
            return delta * pageSize;
        }

        return delta;
    }

    function scrollAxis(container, property, delta, max) {
        if (!delta || max <= 0) {
            return false;
        }

        var previous = container[property];
        var next = Math.max(0, Math.min(max, previous + delta));

        if (next === previous) {
            return false;
        }

        container[property] = next;
        return true;
    }

    function shouldIgnoreWheel(target) {
        if (!isElement(target)) {
            return false;
        }

        return Boolean(target.closest(
            '.select2-container, .select2-dropdown, .dropdown-menu, textarea, input, select, [contenteditable="true"], .flatpickr-calendar'
        ));
    }

    function activateTableScroll(target) {
        var container = primeContainer(getClosestContainer(target));

        setActiveContainer(container);

        if (container) {
            container.focus({ preventScroll: true });
        }
    }

    function handleWheel(event) {
        if (!activeContainer || !activeContainer.isConnected) {
            setActiveContainer(null);
            return;
        }

        if (!activeContainer.contains(event.target) || shouldIgnoreWheel(event.target)) {
            return;
        }

        var canScrollX = activeContainer.scrollWidth > activeContainer.clientWidth + 1;
        var canScrollY = activeContainer.scrollHeight > activeContainer.clientHeight + 1;

        if (!canScrollX && !canScrollY) {
            return;
        }

        var deltaX = normalizeDelta(event.deltaX, event.deltaMode, activeContainer.clientWidth);
        var deltaY = normalizeDelta(event.deltaY, event.deltaMode, activeContainer.clientHeight);
        var maxLeft = activeContainer.scrollWidth - activeContainer.clientWidth;
        var maxTop = activeContainer.scrollHeight - activeContainer.clientHeight;
        var scrolled = false;
        var preferHorizontal = canScrollX && (!canScrollY || event.shiftKey || Math.abs(deltaX) > Math.abs(deltaY));

        if (preferHorizontal) {
            scrolled = scrollAxis(
                activeContainer,
                'scrollLeft',
                Math.abs(deltaX) > 0 ? deltaX : deltaY,
                maxLeft
            );

            if (!scrolled && canScrollY) {
                scrolled = scrollAxis(activeContainer, 'scrollTop', deltaY, maxTop);
            }
        } else {
            scrolled = scrollAxis(activeContainer, 'scrollTop', deltaY, maxTop);

            if (!scrolled && canScrollX) {
                scrolled = scrollAxis(
                    activeContainer,
                    'scrollLeft',
                    Math.abs(deltaX) > 0 ? deltaX : deltaY,
                    maxLeft
                );
            }
        }

        if (scrolled) {
            event.preventDefault();
        }
    }

    /**
     * Walk from el up to .content measuring ALL space needed below el:
     *  - sibling elements after el at each ancestor level
     *  - padding-bottom, border-bottom at each ancestor level
     * This ensures DataTables pagination/info are never hidden,
     * regardless of how deeply nested they are.
     */
    function getSpaceNeededBelow(el) {
        var total = 0;
        var current = el;
        var boundary = el.closest('.content') || document.body;

        while (current && current !== boundary) {
            // Sum heights of all siblings AFTER current element
            var sibling = current.nextElementSibling;
            while (sibling) {
                var sibStyle = window.getComputedStyle(sibling);
                total += sibling.offsetHeight || 0;
                total += parseFloat(sibStyle.marginTop) || 0;
                total += parseFloat(sibStyle.marginBottom) || 0;
                sibling = sibling.nextElementSibling;
            }

            // Add parent's padding-bottom and border-bottom
            var parent = current.parentElement;
            if (parent && parent !== boundary) {
                var pStyle = window.getComputedStyle(parent);
                total += parseFloat(pStyle.paddingBottom) || 0;
                total += parseFloat(pStyle.borderBottomWidth) || 0;
            }

            current = parent;
        }

        return total;
    }

    function fitTableHeight() {
        document.querySelectorAll('.content ' + TABLE_SCROLL_SELECTOR).forEach(function (el) {
            // Skip tables inside modals
            if (el.closest('.modal')) return;
            // Skip tables with explicit inline max-height (sub-tables in modals etc)
            if (el.hasAttribute('style') && el.style.maxHeight && el.dataset.autoFit !== 'true') return;

            var rect = el.getBoundingClientRect();
            var spaceBelow = getSpaceNeededBelow(el);
            var available = window.innerHeight - rect.top - spaceBelow - BOTTOM_MARGIN;
            el.style.maxHeight = Math.max(MIN_TABLE_HEIGHT, available) + 'px';
            el.dataset.autoFit = 'true';
        });
    }

    function restoreTableScroll() {
        document.querySelectorAll('.content ' + TABLE_SCROLL_SELECTOR).forEach(function(el, index) {
            var scrollKey = 'tableScrollTop_' + window.location.pathname + '_' + index;
            var savedPos = sessionStorage.getItem(scrollKey);
            if (savedPos !== null) {
                setTimeout(function() {
                    el.scrollTop = parseInt(savedPos, 10);
                }, 200);
            }
        });
    }

    // Save table scroll position before reload
    window.addEventListener('beforeunload', function() {
        document.querySelectorAll('.content ' + TABLE_SCROLL_SELECTOR).forEach(function(el, index) {
            sessionStorage.setItem('tableScrollTop_' + window.location.pathname + '_' + index, el.scrollTop);
        });
    });

    function prepareExistingTables() {
        document.querySelectorAll(TABLE_SCROLL_SELECTOR).forEach(primeContainer);
        fitTableHeight();
        restoreTableScroll();
    }

    document.addEventListener('pointerdown', function (event) {
        if (getClosestContainer(event.target)) {
            activateTableScroll(event.target);
            return;
        }

        setActiveContainer(null);
    }, true);

    document.addEventListener('wheel', handleWheel, { passive: false });
    window.addEventListener('resize', fitTableHeight);

    // Recalculate on scroll (throttled via rAF)
    var scrollTicking = false;
    window.addEventListener('scroll', function () {
        if (!scrollTicking) {
            scrollTicking = true;
            requestAnimationFrame(function () {
                fitTableHeight();
                scrollTicking = false;
            });
        }
    }, true);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', prepareExistingTables);
    } else {
        prepareExistingTables();
    }

    // Expose for AJAX reloads
    window.fitTableHeight = fitTableHeight;

    // Watch for DOM mutations (DataTables adding pagination etc)
    var observerTimer = null;
    var observer = new MutationObserver(function () {
        clearTimeout(observerTimer);
        observerTimer = setTimeout(fitTableHeight, 100);
    });

    function startObserver() {
        var content = document.querySelector('.content');
        if (content) {
            observer.observe(content, { childList: true, subtree: true });
        }
    }

    startObserver();

    // Auto-hide DataTables pagination when there is only 1 page
    if (typeof jQuery !== 'undefined' && jQuery.fn.dataTable) {
        // Inject CSS
        var style = document.createElement('style');
        style.innerHTML =
            '.dt-hide-pagination { display: none !important; }' +
            '.dataTables_wrapper.dt-no-pages .row:last-child { display: none !important; }';
        document.head.appendChild(style);

        function toggleDtPagination(api) {
            try {
                var container = jQuery(api.table().container());
                if (!api.init().paging) return;

                var pageInfo = api.page.info();

                if (pageInfo.pages <= 1) {
                    container.addClass('dt-no-pages');
                    container.find('.dataTables_paginate, .dataTables_info').addClass('dt-hide-pagination');
                } else {
                    container.removeClass('dt-no-pages');
                    container.find('.dataTables_paginate, .dataTables_info').removeClass('dt-hide-pagination');
                }
            } catch (err) {
                // silently ignore
            }
        }

        jQuery(document).on('draw.dt', function (e, settings) {
            toggleDtPagination(new jQuery.fn.dataTable.Api(settings));
            setTimeout(fitTableHeight, 50);
        });

        jQuery(function() {
            setTimeout(function() {
                if (jQuery.fn.dataTable.tables) {
                    var api = new jQuery.fn.dataTable.Api(jQuery.fn.dataTable.tables());
                    api.iterator('table', function (settings) {
                        toggleDtPagination(new jQuery.fn.dataTable.Api(settings));
                    });
                }
                fitTableHeight();
            }, 100);
        });
    }
})();
