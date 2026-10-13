/**
 * Review Toast System - Injected Content Script
 * Displays a review prompt toast on the web page (Netflix, YouTube, etc.)
 * Positioned at top-center with elegant popup-style UI
 */
;(function () {
  'use strict'

  // Prevent multiple injections
  if (window.reviewToastSystem) {
    console.log('[ReviewToast] System already loaded')
    return
  }

  const TOAST_ID = 'sd-review-toast-container'
  let currentToast = null
  let autoDismissTimer = null
  let progressInterval = null
  const AUTO_DISMISS_DELAY = 20000 // 20 seconds

  /**
   * Create and show the review toast
   * @param {Object} config - Toast configuration
   */
  function showReviewToast(config) {
    console.log('[ReviewToast] Showing toast', config)

    // If already exists, just reset the timer and return
    if (currentToast) {
      console.log('[ReviewToast] Toast already visible, resetting timer')
      const progressBar = currentToast.querySelector('.sd-progress-bar')
      if (progressBar) {
        progressBar.style.width = '0%'
        clearTimers()
        startAutoDismiss(progressBar)
      }
      return
    }

    // Create container
    const container = document.createElement('div')
    container.id = TOAST_ID
    container.setAttribute('data-sd-review-toast', 'true')

    // Container styles (top-center overlay)
    container.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      z-index: 2147483647;
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding-top: 60px;
      pointer-events: none;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
    `

    // Create toast card
    const toast = document.createElement('div')
    toast.style.cssText = `
      background: #1e1e1e;
      border: 1px solid #3e3e3e;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4);
      max-width: 400px;
      width: 90%;
      pointer-events: auto;
      transform: translateY(-100px);
      opacity: 0;
      transition: all 0.5s cubic-bezier(0.19, 1, 0.22, 1);
      position: relative;
      overflow: hidden;
      color: white;
    `

    // Close button
    const closeBtn = document.createElement('button')
    closeBtn.innerHTML = '×'
    closeBtn.style.cssText = `
      position: absolute;
      top: 10px;
      right: 10px;
      background: transparent;
      border: none;
      color: #888;
      font-size: 24px;
      width: 28px;
      height: 28px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
      line-height: 1;
    `
    closeBtn.onmouseover = () => {
      closeBtn.style.color = 'white'
      closeBtn.style.background = 'rgba(255, 255, 255, 0.1)'
      closeBtn.style.borderRadius = '4px'
    }
    closeBtn.onmouseout = () => {
      closeBtn.style.color = '#888'
      closeBtn.style.background = 'transparent'
    }
    closeBtn.onclick = () => {
      console.log('[ReviewToast] Close button clicked - dismissing without action')
      removeToast()
    }

    // Header
    const header = document.createElement('div')
    header.style.cssText = `
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 8px;
      padding-right: 30px;
    `

    const starIcon = document.createElement('span')
    starIcon.innerHTML = '⭐'
    starIcon.style.cssText = `
      font-size: 24px;
    `

    const title = document.createElement('h3')
    title.textContent = config.title || 'Enjoying the extension?'
    title.style.cssText = `
      margin: 0;
      font-size: 17px;
      font-weight: 600;
      color: white;
    `

    header.appendChild(starIcon)
    header.appendChild(title)

    // Message
    const message = document.createElement('p')
    message.textContent = config.message || 'A quick review really helps us grow!'
    message.style.cssText = `
      margin: 0 0 18px 0;
      font-size: 14px;
      color: #b0b0b0;
      line-height: 1.5;
    `

    // Buttons container
    const buttonsContainer = document.createElement('div')
    buttonsContainer.style.cssText = `
      display: flex;
      gap: 8px;
    `

    // Helper to create buttons
    function createButton(text, isPrimary, action) {
      const btn = document.createElement('button')
      btn.textContent = text
      btn.style.cssText = `
        flex: 1;
        padding: 8px 12px;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        transition: all 0.2s;
        border: none;
        ${
          isPrimary
            ? `
          background: #3b82f6;
          color: white;
        `
            : `
          background: transparent;
          color: #888;
          border: 1px solid #3e3e3e;
        `
        }
      `

      btn.onmouseover = () => {
        if (isPrimary) {
          btn.style.background = '#2563eb'
          btn.style.transform = 'translateY(-1px)'
        } else {
          btn.style.background = '#2e2e2e'
          btn.style.borderColor = '#4e4e4e'
          btn.style.color = 'white'
        }
      }

      btn.onmouseout = () => {
        if (isPrimary) {
          btn.style.background = '#3b82f6'
          btn.style.transform = 'translateY(0)'
        } else {
          btn.style.background = 'transparent'
          btn.style.borderColor = '#3e3e3e'
          btn.style.color = '#888'
        }
      }

      btn.onclick = () => handleAction(action)

      return btn
    }

    const btnAlreadyDid = createButton(config.btnAlreadyDid || 'Already did', false, 'alreadyDid')
    const btnMaybeLater = createButton(config.btnMaybeLater || 'Maybe later', false, 'later')
    const btnLeaveReview = createButton(
      config.btnLeaveReview || 'Leave review ⭐⭐⭐⭐⭐',
      true,
      'review'
    )

    buttonsContainer.appendChild(btnAlreadyDid)
    buttonsContainer.appendChild(btnMaybeLater)
    buttonsContainer.appendChild(btnLeaveReview)

    // Progress bar
    const progressBar = document.createElement('div')
    progressBar.className = 'sd-progress-bar'
    progressBar.style.cssText = `
      position: absolute;
      bottom: 0;
      left: 0;
      height: 3px;
      width: 0%;
      background: linear-gradient(90deg, #3b82f6, #8b5cf6);
      transition: width 0.1s linear;
    `

    // Assemble toast
    toast.appendChild(closeBtn)
    toast.appendChild(header)
    toast.appendChild(message)
    toast.appendChild(buttonsContainer)
    toast.appendChild(progressBar)
    container.appendChild(toast)

    // Add to page
    document.body.appendChild(container)
    currentToast = container

    // Animate in
    requestAnimationFrame(() => {
      toast.style.transform = 'translateY(0)'
      toast.style.opacity = '1'
    })

    // Start auto-dismiss timer
    startAutoDismiss(progressBar)
  }

  /**
   * Start auto-dismiss countdown (20 seconds)
   */
  function startAutoDismiss(progressBar) {
    const startTime = Date.now()

    progressInterval = setInterval(() => {
      const elapsed = Date.now() - startTime
      const progress = (elapsed / AUTO_DISMISS_DELAY) * 100
      progressBar.style.width = Math.min(progress, 100) + '%'
    }, 100)

    autoDismissTimer = setTimeout(() => {
      console.log('[ReviewToast] Auto-dismiss triggered - closing without action')
      removeToast()
    }, AUTO_DISMISS_DELAY)
  }

  /**
   * Clear auto-dismiss timers
   */
  function clearTimers() {
    if (autoDismissTimer) clearTimeout(autoDismissTimer)
    if (progressInterval) clearInterval(progressInterval)
  }

  /**
   * Handle button actions
   */
  function handleAction(action) {
    console.log('[ReviewToast] Action:', action)
    clearTimers()
    // Send message to content script via window.postMessage
    window.postMessage(
      {
        type: 'SD_REVIEW_TOAST_ACTION',
        action: action,
      },
      '*'
    )
    removeToast()
  }

  /**
   * Remove toast from page
   */
  function removeToast() {
    if (currentToast) {
      const toast = currentToast.querySelector('div')
      if (toast) {
        toast.style.transform = 'translateY(-100px)'
        toast.style.opacity = '0'
        setTimeout(() => {
          if (currentToast && currentToast.parentNode) {
            currentToast.parentNode.removeChild(currentToast)
          }
          currentToast = null
        }, 500)
      }
    }
    clearTimers()
  }

  // Expose API
  window.reviewToastSystem = {
    show: showReviewToast,
    hide: removeToast,
  }

  // Listen for custom event from content script (avoids CSP violations)
  window.addEventListener('showReviewToast', function (event) {
    console.log('[ReviewToast] Received showReviewToast event')
    if (event.detail) {
      showReviewToast(event.detail)
    }
  })

  console.log('[ReviewToast] System initialized')
})()
