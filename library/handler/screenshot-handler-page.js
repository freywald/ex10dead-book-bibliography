(async () => {
	const MAX_H = Number(window.__SCREENSHOT_MAX_HEIGHT__) || 16000;
	const VIEWPORT_FALLBACK = Number(window.__SCREENSHOT_VIEWPORT_HEIGHT__) || 800;
	const ABOVE_POST_COUNT = 3;
	const STEP_DELAY_MS = 500;
	const REPLY_COUNT = Number(window.__SCREENSHOT_REPLY_COUNT__);
	const replyCount = Number.isFinite(REPLY_COUNT) && REPLY_COUNT >= 0 ? REPLY_COUNT : 3;

	const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
	const sleepBetweenImages = () => sleep(1000 + Math.floor(Math.random() * 4001));

	const host = location.hostname.replace(/^www\./i, "").toLowerCase();
	const isTwitter = host === "x.com" || host === "twitter.com";

	const failedResources = new Set();
	const logFailedResource = (status, url) => {
		const address = String(url || "");
		if (!address) {
			return;
		}
		const line = status + " " + address;
		if (failedResources.has(line)) {
			return;
		}
		failedResources.add(line);
		console.log("resource failed", line);
	};
	window.addEventListener("error", (event) => {
		const target = event.target;
		if (!target || target === window) {
			return;
		}
		logFailedResource("element", target.currentSrc || target.src || target.href || "");
	}, true);
	const logResourceTimings = () => {
		for (const entry of performance.getEntriesByType("resource")) {
			const status = entry.responseStatus;
			if (status >= 400) {
				logFailedResource(status, entry.name);
			} else if (status === 0 && entry.transferSize === 0 && entry.decodedBodySize === 0) {
				logFailedResource("no-status", entry.name);
			}
		}
	};

	const docH = () => Math.max(
		document.body ? document.body.scrollHeight : 0,
		document.documentElement.scrollHeight,
		document.documentElement.offsetHeight
	);

	const statusIdFromHref = (href) => {
		const match = String(href || "").match(/\/status\/(\d+)/);
		return match ? match[1] : "";
	};

	const focalId = statusIdFromHref(location.pathname);

	const inQuote = (el) => !!el.closest('[data-testid="quoteTweet"], [data-testid="card.wrapper"]');

	const ownStatusId = (article) => {
		const times = [...article.querySelectorAll("time")].filter((time) => !inQuote(time));
		for (const time of times) {
			const link = time.closest('a[href*="/status/"]');
			const id = statusIdFromHref(link && (link.getAttribute("href") || link.href));
			if (id) {
				return id;
			}
		}
		const links = [...article.querySelectorAll('a[href*="/status/"]')].filter((link) => !inQuote(link));
		for (const link of links) {
			if (!link.querySelector("time")) {
				continue;
			}
			const id = statusIdFromHref(link.getAttribute("href") || link.href);
			if (id) {
				return id;
			}
		}
		return statusIdFromHref(links[0] && (links[0].getAttribute("href") || links[0].href));
	};

	const tweetKey = (article) => ownStatusId(article) || article.innerText.slice(0, 120);

	const sizedUrl = (url, name) => {
		try {
			const parsed = new URL(url, location.href);
			if (!parsed.hostname.endsWith("twimg.com")) {
				return url;
			}
			parsed.searchParams.set("name", name);
			parsed.pathname = parsed.pathname.replace(/:(small|medium|large|thumb|orig)$/, ":" + name);
			return parsed.href;
		} catch (e) {
			return url;
		}
	};

	const bestUrl = (url) => sizedUrl(url, /video_thumb/.test(url) ? "large" : "orig");

	const thumbFromText = (text) => {
		const match = String(text || "").match(/https?:\/\/pbs\.twimg\.com\/(?:ext_tw_video_thumb|amplify_video_thumb|tweet_video_thumb|video_thumb)\/[^"'\\\s)]+/);
		return match ? match[0].replace(/&amp;/g, "&") : "";
	};

	const thumbFromElement = (el) => {
		if (!el) {
			return "";
		}
		const bg = getComputedStyle(el).backgroundImage || "";
		const bgMatch = bg.match(/url\(["']?(https?:\/\/[^"')]+)/);
		if (bgMatch && /video_thumb|pbs\.twimg\.com\/media\//.test(bgMatch[1])) {
			return bgMatch[1];
		}
		if (el.tagName === "IMG") {
			const src = el.currentSrc || el.src || "";
			if (/^https?:/i.test(src) && /video_thumb|pbs\.twimg\.com\/media\//.test(src)) {
				return src;
			}
		}
		if (el.tagName === "VIDEO") {
			const poster = el.getAttribute("poster") || el.poster || "";
			if (/^https?:/i.test(poster)) {
				return poster;
			}
		}
		return thumbFromText(el.getAttribute("style") || "") || thumbFromText(el.outerHTML || "");
	};

	const loadImage = async (img, src) => {
		img.removeAttribute("srcset");
		if (!src || src === img.src) {
			return false;
		}
		await sleepBetweenImages();
		img.src = src;
		if (img.decode) {
			try {
				await img.decode();
			} catch (e) {}
		}
		return true;
	};

	const upgradeImages = async (root) => {
		const imgs = [...root.querySelectorAll(
			'img[src*="pbs.twimg.com/media/"], img[src*="video_thumb"]'
		)];
		for (const img of imgs) {
			if (img.dataset.screenshotSized === "1") {
				continue;
			}
			const src = bestUrl(img.currentSrc || img.src);
			const loaded = await loadImage(img, src);
			if (loaded || src === img.src) {
				img.dataset.screenshotSized = "1";
			}
		}
	};

	const replaceVideosWithPosters = async (root) => {
		const players = [...root.querySelectorAll(
			'[data-testid="videoPlayer"], [data-testid="videoComponent"], [data-testid="previewInterstitial"], [data-testid="tweetPhoto"]'
		)].filter((player) =>
			player.querySelector("video, button[aria-label*='Play'], [data-testid='videoPlayer']")
			|| /video_thumb/.test(player.innerHTML)
		);
		for (const player of players) {
			if (player.dataset.screenshotStill === "1") {
				continue;
			}
			let url = "";
			for (const el of [player, ...player.querySelectorAll("video, img, div")]) {
				url = thumbFromElement(el);
				if (url) {
					break;
				}
			}
			if (!url) {
				console.log("video poster missing");
				continue;
			}
			const img = document.createElement("img");
			img.alt = "video preview";
			img.dataset.screenshotSized = "1";
			img.style.setProperty("position", "absolute", "important");
			img.style.setProperty("inset", "0", "important");
			img.style.setProperty("width", "100%", "important");
			img.style.setProperty("height", "100%", "important");
			img.style.setProperty("object-fit", "cover", "important");
			img.style.setProperty("z-index", "5", "important");
			player.style.setProperty("position", "relative", "important");
			player.querySelectorAll("video").forEach((video) => {
				video.style.setProperty("display", "none", "important");
			});
			player.appendChild(img);
			await loadImage(img, bestUrl(url));
			player.dataset.screenshotStill = "1";
		}
		await upgradeImages(root);
	};

	const clickInPlace = (el) => {
		if (!el || el.dataset.screenshotClicked === "1") {
			return;
		}
		if (el.tagName === "A" || el.closest("a[href]")) {
			return;
		}
		el.dataset.screenshotClicked = "1";
		el.click();
	};

	const isReportedPlaceholder = (article) =>
		/you reported this post/i.test(article.innerText || "") && !ownStatusId(article);

	const revealReportedPosts = () => {
		document.querySelectorAll("button").forEach((button) => {
			const label = (button.innerText || "").replace(/\s+/g, " ").trim();
			if (!/^view$/i.test(label)) {
				return;
			}
			let node = button;
			for (let i = 0; i < 6 && node; i += 1) {
				if (/you reported this post/i.test(node.innerText || "")) {
					clickInPlace(button);
					return;
				}
				node = node.parentElement;
			}
		});
	};

	const expandTweet = (tweet) => {
		clickInPlace(tweet.querySelector("button[data-testid='tweet-text-show-more-link']"));

		tweet.querySelectorAll("button[type='button']").forEach((button) => {
			const label = (button.innerText || "").replace(/\s+/g, " ").trim();
			if (/^show more$/i.test(label)) {
				clickInPlace(button);
			}
		});

		const quotedTweet = tweet.querySelector("div[id^='id__'][aria-labelledby^='id__']");
		if (!quotedTweet) {
			return;
		}
		const quotedText = quotedTweet.querySelector("div[data-testid='tweetText']");
		if (!quotedText) {
			return;
		}
		quotedText.style.removeProperty("-webkit-line-clamp");
		quotedText.style.setProperty("-webkit-line-clamp", "unset", "important");
		quotedText.style.setProperty("max-height", "none", "important");
	};

	const expandReplySections = () => {
		document.querySelectorAll('button, div[role="button"]').forEach((button) => {
			const label = (button.innerText || "").replace(/\s+/g, " ").trim();
			if (/^show (more )?replies$/i.test(label)) {
				clickInPlace(button);
			}
		});
	};

	const expandAllVisible = () => {
		expandReplySections();
		document.querySelectorAll("article").forEach(expandTweet);
	};

	const ZOOM = Number(window.__SCREENSHOT_ZOOM__) || 1;
	if (document.documentElement.style.zoom !== undefined) {
		document.documentElement.style.zoom = String(ZOOM);
	}

	const hide = (el) => {
		if (!el || !el.style) {
			return;
		}
		el.style.setProperty("display", "none", "important");
	};

	const stash = [];
	const seen = new Set();
	const articleRoot = () =>
		document.querySelector('[data-testid="primaryColumn"]') || document;

	const collect = () => {
		if (!isTwitter) {
			return;
		}
		const rows = [...articleRoot().querySelectorAll("article")].map((article) => ({
			article,
			key: tweetKey(article),
			top: article.getBoundingClientRect().top + window.scrollY
		}));
		rows.sort((a, b) => a.top - b.top);
		rows.forEach((row) => {
			if (!row.key || seen.has(row.key) || isReportedPlaceholder(row.article)) {
				return;
			}
			seen.add(row.key);
			stash.push(row.article.cloneNode(true));
		});
	};

	if (isTwitter) {
		revealReportedPosts();
		expandAllVisible();
		await sleep(STEP_DELAY_MS);
		collect();
	}

	const step = Math.max(200, Math.floor((window.innerHeight || VIEWPORT_FALLBACK) * 0.85));
	let y = 0;
	let lastSize = -1;
	let lastHeight = -1;
	let stable = 0;

	while (y < MAX_H && stable < 6) {
		window.scrollTo(0, y);
		await sleep(STEP_DELAY_MS);
		if (isTwitter) {
			revealReportedPosts();
			expandAllVisible();
			await sleep(STEP_DELAY_MS);
			collect();
			console.log("stashed", stash.length, "visible", articleRoot().querySelectorAll("article").length, "y", y);
			if (stash.length === lastSize) {
				stable += 1;
			} else {
				stable = 0;
			}
			lastSize = stash.length;

			const focalAt = focalId
				? stash.findIndex((node) => tweetKey(node) === focalId)
				: -1;
			if (focalAt >= 0 && stash.length - focalAt - 1 >= replyCount) {
				break;
			}
		} else {
			const height = Math.min(docH(), MAX_H);
			console.log("scroll", y, "docH", height);
			if (height === lastHeight) {
				stable += 1;
			} else {
				stable = 0;
			}
			lastHeight = height;
		}
		const height = Math.min(docH(), MAX_H);
		if (y >= height) {
			break;
		}
		y = Math.min(y + step, height, MAX_H);
	}

	window.scrollTo(0, 0);
	await sleep(100);

	if (isTwitter) {
		if (focalId) {
			let focalAt = stash.findIndex((node) => tweetKey(node) === focalId);
			if (focalAt < 0) {
				const live = [...articleRoot().querySelectorAll("article")].find((article) => tweetKey(article) === focalId);
				if (live) {
					stash.unshift(live.cloneNode(true));
					focalAt = 0;
				}
			}
			if (focalAt < 0) {
				console.log("focal missing", focalId, stash.slice(0, 12).map(tweetKey));
				throw new Error("screenshot: focal tweet not found: " + focalId);
			}
			const start = Math.max(0, focalAt - ABOVE_POST_COUNT);
			stash.splice(0, start);
			const focalNow = focalAt - start;
			stash.splice(focalNow + 1 + replyCount);
		}

		const col = document.querySelector('[data-testid="primaryColumn"]');
		if (col && stash.length) {
			const holder = document.createElement("div");
			holder.setAttribute("data-screenshot-thread", "1");
			stash.forEach((node) => holder.appendChild(node));
			col.replaceChildren(holder);
			await replaceVideosWithPosters(holder);
		}

		document.querySelectorAll([
			'header[role="banner"]',
			'nav[aria-label="Primary"]',
			'[data-testid="sidebarColumn"]',
			'[data-testid="DMDrawer"]',
			'[data-testid="BottomBar"]',
			'[data-testid="placementTracking"]',
			'[data-testid="mask"]',
			'[data-testid="sheetDialog"]',
			'[data-testid="confirmationSheetDialog"]',
			'[aria-label="Trending"]',
			'[data-testid="cookiePrompt"]'
		].join(",")).forEach(hide);
	}

	logResourceTimings();
	document.documentElement.setAttribute("data-screenshot-ready", "1");
})();
