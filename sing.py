
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import os
import json
from datetime import datetime
import aiohttp
import re

class MusicSearchView(discord.ui.View):
    def __init__(self, bot, user_id, search_results):
        super().__init__(timeout=300)
        self.bot = bot
        self.user_id = user_id
        self.search_results = search_results
        
        # Tạo select menu với kết quả tìm kiếm
        options = []
        for i, result in enumerate(search_results[:10]):  # Giới hạn 10 kết quả
            title = result.get('title', 'Không có tiêu đề')
            channel = result.get('uploader', 'Không rõ kênh')
            duration = result.get('duration_string', 'N/A')
            
            # Cắt ngắn title nếu quá dài
            if len(title) > 80:
                title = title[:77] + "..."
                
            options.append(
                discord.SelectOption(
                    label=f"{i+1}. {title[:50]}...",
                    value=str(i),
                    description=f"Kênh: {channel[:50]} | {duration}"
                )
            )
        
        if options:
            self.add_item(MusicSelectMenu(options, search_results))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải menu của bạn!", ephemeral=True)
            return False
        return True

class MusicSelectMenu(discord.ui.Select):
    def __init__(self, options, search_results):
        super().__init__(
            placeholder="Chọn bài hát bạn muốn tải...",
            min_values=1,
            max_values=1,
            options=options
        )
        self.search_results = search_results

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            
            selected_index = int(self.values[0])
            selected_song = self.search_results[selected_index]
            
            # Tạo embed thông báo đang tải
            processing_embed = discord.Embed(
                title="🎵 Đang tải nhạc...",
                description=f"**{selected_song.get('title', 'Không có tiêu đề')}**\n\n⏳ Vui lòng chờ trong giây lát...",
                color=discord.Color.blue()
            )
            
            processing_msg = await interaction.followup.send(embed=processing_embed)
            
            # Tải và gửi file nhạc
            await self.download_and_send_music(interaction, selected_song, processing_msg)
            
        except Exception as e:
            print(f"Lỗi trong callback: {e}")
            try:
                error_embed = discord.Embed(
                    title="❌ Lỗi khi tải nhạc",
                    description=f"Đã xảy ra lỗi: {str(e)}",
                    color=discord.Color.red()
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=error_embed)
                else:
                    await interaction.response.send_message(embed=error_embed)
            except:
                pass

    async def download_and_send_music(self, interaction, song_info, processing_msg=None):
        try:
            url = song_info.get('webpage_url') or song_info.get('url')
            if not url:
                return await interaction.followup.send("❌ Không tìm thấy URL của bài hát!")

            # Tạo thư mục cache nếu chưa có
            os.makedirs("music_cache", exist_ok=True)
            
            # Tạo tên file an toàn (không có extension vì yt-dlp sẽ tự thêm)
            safe_title = re.sub(r'[^\w\s-]', '', song_info.get('title', 'unknown'))[:50]
            filename_base = f"music_cache/{safe_title}_{interaction.user.id}"
            final_filename = f"{filename_base}.mp3"
            
            # Cấu hình yt-dlp
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': filename_base + '.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
            }

            # Tải nhạc trong thread pool để không block bot
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.download_audio, url, ydl_opts)
            
            # Kiểm tra file đã tải
            if not os.path.exists(final_filename):
                return await interaction.followup.send("❌ Không thể tải file nhạc!")
            
            # Kiểm tra kích thước file (Discord limit 8MB cho free)
            file_size = os.path.getsize(final_filename)
            if file_size > 8 * 1024 * 1024:  # 8MB
                os.remove(final_filename)
                return await interaction.followup.send("❌ File quá lớn! Vui lòng chọn bài hát ngắn hơn.")
            
            # Tạo embed thông tin bài hát
            info_embed = discord.Embed(
                title="🎵 Đã tải xong!",
                description=f"**{song_info.get('title', 'Không có tiêu đề')}**",
                color=discord.Color.green()
            )
            
            # Thêm thông tin chi tiết
            if song_info.get('uploader'):
                info_embed.add_field(name="🎤 Kênh", value=song_info['uploader'], inline=True)
            
            if song_info.get('duration_string'):
                info_embed.add_field(name="⏰ Thời lượng", value=song_info['duration_string'], inline=True)
            
            if song_info.get('view_count'):
                view_count = f"{song_info['view_count']:,}" if isinstance(song_info['view_count'], int) else song_info['view_count']
                info_embed.add_field(name="👀 Lượt xem", value=view_count, inline=True)
            
            info_embed.set_footer(text=f"Yêu cầu bởi {interaction.user.display_name}")
            
            # Gửi file nhạc
            with open(final_filename, 'rb') as f:
                discord_file = discord.File(f, filename=f"{safe_title}.mp3")
                await interaction.followup.send(embed=info_embed, file=discord_file)
            
            # Xóa file sau khi gửi
            if os.path.exists(final_filename):
                os.remove(final_filename)
                
        except Exception as e:
            # Cleanup file nếu có lỗi
            if 'final_filename' in locals() and os.path.exists(final_filename):
                os.remove(final_filename)
            
            await interaction.followup.send(f"❌ Lỗi khi tải nhạc: {str(e)}")

    def download_audio(self, url, ydl_opts):
        """Hàm tải nhạc (chạy trong thread pool)"""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

class MusicSearch(commands.Cog):
    """Tìm kiếm và tải nhạc từ YouTube"""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="sing", help="Tìm kiếm và tải nhạc từ YouTube")
    @commands.cooldown(1, 30, commands.BucketType.user)  # Cooldown 30 giây
    async def sing(self, ctx, *, query: str = None):
        """Lệnh tìm kiếm và tải nhạc từ YouTube"""
        
        if not query:
            embed = discord.Embed(
                title="🎵 Lệnh Sing - Tải nhạc YouTube",
                description="**Cách sử dụng:**\n`!sing <tên bài hát>` - Tìm kiếm bài hát\n`!sing <link YouTube>` - Tải trực tiếp từ link",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="📝 Ví dụ:",
                value="• `!sing sơn tùng remix`\n• `!sing https://youtube.com/watch?v=...`",
                inline=False
            )
            return await ctx.send(embed=embed)

        # Hiển thị thông báo đang tìm kiếm
        searching_embed = discord.Embed(
            title="🔍 Đang tìm kiếm...",
            description=f"Đang tìm kiếm: **{query}**\n⏳ Vui lòng chờ...",
            color=discord.Color.blue()
        )
        search_msg = await ctx.send(embed=searching_embed)

        try:
            # Kiểm tra nếu là link YouTube
            if 'youtube.com' in query or 'youtu.be' in query:
                await self.download_direct_link(ctx, query, search_msg)
            else:
                await self.search_and_display_results(ctx, query, search_msg)
                
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Lỗi tìm kiếm",
                description=f"Đã xảy ra lỗi: {str(e)}",
                color=discord.Color.red()
            )
            await search_msg.edit(embed=error_embed)

    async def search_and_display_results(self, ctx, query, search_msg):
        """Tìm kiếm và hiển thị kết quả"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'default_search': 'ytsearch10:',  # Tìm 10 kết quả
            }
            
            # Tìm kiếm trong thread pool
            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(
                None, self.search_youtube, f"ytsearch10:{query}", ydl_opts
            )
            
            if not search_results:
                no_results_embed = discord.Embed(
                    title="😕 Không tìm thấy kết quả",
                    description=f"Không tìm thấy bài hát nào cho: **{query}**",
                    color=discord.Color.orange()
                )
                return await search_msg.edit(embed=no_results_embed)
            
            # Tạo embed hiển thị kết quả
            results_embed = discord.Embed(
                title="🎵 Kết quả tìm kiếm",
                description=f"Tìm thấy **{len(search_results)}** kết quả cho: **{query}**",
                color=discord.Color.green()
            )
            
            # Hiển thị 5 kết quả đầu tiên trong embed
            for i, result in enumerate(search_results[:5]):
                title = result.get('title', 'Không có tiêu đề')
                uploader = result.get('uploader', 'Không rõ')
                duration = result.get('duration_string', 'N/A')
                
                results_embed.add_field(
                    name=f"{i+1}. {title[:60]}{'...' if len(title) > 60 else ''}",
                    value=f"👤 {uploader}\n⏰ {duration}",
                    inline=False
                )
            
            results_embed.set_footer(text="Sử dụng menu dropdown bên dưới để chọn bài hát")
            
            # Tạo view với select menu
            view = MusicSearchView(self.bot, ctx.author.id, search_results)
            
            await search_msg.edit(embed=results_embed, view=view)
            
        except Exception as e:
            raise e

    async def download_direct_link(self, ctx, url, search_msg):
        """Tải trực tiếp từ link YouTube"""
        try:
            # Cập nhật thông báo
            processing_embed = discord.Embed(
                title="⏬ Đang tải từ link...",
                description=f"**Link:** {url}\n⏳ Vui lòng chờ...",
                color=discord.Color.blue()
            )
            await search_msg.edit(embed=processing_embed)
            
            # Lấy thông tin video
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }
            
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, self.get_video_info, url, ydl_opts)
            
            if not info:
                return await search_msg.edit(embed=discord.Embed(
                    title="❌ Lỗi",
                    description="Không thể lấy thông tin video!",
                    color=discord.Color.red()
                ))
            
            # Tải file nhạc
            await self.download_and_send_music_direct(ctx, search_msg, info, url)
            
        except Exception as e:
            raise e

    def search_youtube(self, query, ydl_opts):
        """Tìm kiếm YouTube (chạy trong thread pool)"""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            results = ydl.extract_info(query, download=False)
            if 'entries' in results:
                return results['entries']
            return []

    def get_video_info(self, url, ydl_opts):
        """Lấy thông tin video (chạy trong thread pool)"""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    async def download_and_send_music_direct(self, ctx, search_msg, info, url):
        """Tải và gửi nhạc trực tiếp"""
        try:
            # Tạo thư mục cache
            os.makedirs("music_cache", exist_ok=True)
            
            # Tạo tên file an toàn
            safe_title = re.sub(r'[^\w\s-]', '', info.get('title', 'unknown'))[:50]
            filename_base = f"music_cache/{safe_title}_{ctx.author.id}"
            final_filename = f"{filename_base}.mp3"
            
            # Cấu hình tải
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': filename_base + '.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
            }
            
            # Tải file
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self.download_audio_direct, url, ydl_opts)
            
            # Kiểm tra file
            if not os.path.exists(final_filename):
                return await search_msg.edit(embed=discord.Embed(
                    title="❌ Lỗi",
                    description="Không thể tải file nhạc!",
                    color=discord.Color.red()
                ))
            
            # Kiểm tra kích thước
            file_size = os.path.getsize(final_filename)
            if file_size > 8 * 1024 * 1024:  # 8MB
                os.remove(final_filename)
                return await search_msg.edit(embed=discord.Embed(
                    title="❌ File quá lớn",
                    description="File vượt quá 8MB. Vui lòng chọn bài hát ngắn hơn!",
                    color=discord.Color.red()
                ))
            
            # Tạo embed kết quả
            success_embed = discord.Embed(
                title="🎵 Tải thành công!",
                description=f"**{info.get('title', 'Không có tiêu đề')}**",
                color=discord.Color.green()
            )
            
            if info.get('uploader'):
                success_embed.add_field(name="🎤 Kênh", value=info['uploader'], inline=True)
            
            if info.get('duration_string'):
                success_embed.add_field(name="⏰ Thời lượng", value=info['duration_string'], inline=True)
            
            if info.get('view_count'):
                view_count = f"{info['view_count']:,}" if isinstance(info['view_count'], int) else info['view_count']
                success_embed.add_field(name="👀 Lượt xem", value=view_count, inline=True)
            
            success_embed.set_footer(text=f"Yêu cầu bởi {ctx.author.display_name}")
            
            # Gửi file
            with open(final_filename, 'rb') as f:
                discord_file = discord.File(f, filename=f"{safe_title}.mp3")
                await search_msg.edit(embed=success_embed)
                await ctx.send(file=discord_file)
            
            # Cleanup
            if os.path.exists(final_filename):
                os.remove(final_filename)
                
        except Exception as e:
            if 'final_filename' in locals() and os.path.exists(final_filename):
                os.remove(final_filename)
            raise e

    def download_audio_direct(self, url, ydl_opts):
        """Tải audio trực tiếp (chạy trong thread pool)"""
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

async def setup(bot):
    await bot.add_cog(MusicSearch(bot))
