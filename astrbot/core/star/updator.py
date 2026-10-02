import os
import shutil
import zipfile

from astrbot.core import logger
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_path
from astrbot.core.utils.io import on_error, remove_dir

from ..star.star import StarMetadata
from ..updator import RepoZipUpdator


class PluginUpdator(RepoZipUpdator):
    def __init__(self, repo_mirror: str = "", verify: str | bool | None = None) -> None:
        super().__init__(repo_mirror, verify=verify)
        self.plugin_store_path = get_astrbot_plugin_path()

    def get_plugin_store_path(self) -> str:
        return self.plugin_store_path

    async def install(self, repo_url: str, proxy="") -> str:
        _, repo_name, _ = self.parse_github_url(repo_url)
        repo_name = self.format_name(repo_name)
        plugin_path = os.path.join(self.plugin_store_path, repo_name)
        await self.download_from_repo_url(plugin_path, repo_url, proxy)
        self.unzip_file(plugin_path + ".zip", plugin_path)

        return plugin_path

    async def update(self, plugin: StarMetadata, proxy="") -> str:
        repo_url = plugin.repo

        if not repo_url:
            raise Exception(f"插件 {plugin.name} 没有指定仓库地址。")

        if not plugin.root_dir_name:
            raise Exception(f"插件 {plugin.name} 的根目录名未指定。")

        plugin_path = os.path.join(self.plugin_store_path, plugin.root_dir_name)

        logger.info(f"正在更新插件，路径: {plugin_path}，仓库地址: {repo_url}")
        await self.download_from_repo_url(plugin_path, repo_url, proxy=proxy)

        try:
            remove_dir(plugin_path)
        except BaseException as e:
            logger.error(
                f"删除旧版本插件 {plugin_path} 文件夹失败: {e!s}，使用覆盖安装。",
            )

        self.unzip_file(plugin_path + ".zip", plugin_path)

        return plugin_path

    @staticmethod
    def _get_wrapping_dir(namelist: list[str]) -> str:
        """返回压缩包统一的顶层目录名（含结尾的 /），没有则返回空串。

        只有所有条目都位于同一个目录条目之下时才算有顶层目录。不能直接把
        namelist()[0] 当成目录——那样会把根目录下的普通文件（例如 .git）误判成
        目录，进而在 listdir 时抛 NotADirectoryError。
        """
        dir_entries = {n.replace("\\", "/") for n in namelist}
        tops: set[str] = set()
        for name in dir_entries:
            stripped = name.strip("/")
            if not stripped or stripped.startswith("__MACOSX/"):
                continue
            tops.add(stripped.split("/", 1)[0])
            if len(tops) > 1:
                return ""
        if len(tops) != 1:
            return ""
        top = tops.pop()
        return f"{top}/" if f"{top}/" in dir_entries else ""

    def unzip_file(self, zip_path: str, target_dir: str) -> None:
        os.makedirs(target_dir, exist_ok=True)
        logger.info(f"正在解压压缩包: {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as z:
            update_dir = self._get_wrapping_dir(z.namelist())
            z.extractall(target_dir)

        if not update_dir:
            # 压缩包里没有统一的顶层目录（例如直接打包插件目录内容），
            # 文件已经落在 target_dir 下，不需要再上提一层。
            try:
                os.remove(zip_path)
            except BaseException:
                logger.warning(f"删除更新文件失败，可以手动删除 {zip_path}")
            return

        files = os.listdir(os.path.join(target_dir, update_dir))
        for f in files:
            if os.path.isdir(os.path.join(target_dir, update_dir, f)):
                if os.path.exists(os.path.join(target_dir, f)):
                    shutil.rmtree(os.path.join(target_dir, f), onerror=on_error)
            elif os.path.exists(os.path.join(target_dir, f)):
                os.remove(os.path.join(target_dir, f))
            shutil.move(os.path.join(target_dir, update_dir, f), target_dir)

        try:
            logger.info(
                f"删除临时文件: {zip_path} 和 {os.path.join(target_dir, update_dir)}",
            )
            shutil.rmtree(os.path.join(target_dir, update_dir), onerror=on_error)
            os.remove(zip_path)
        except BaseException:
            logger.warning(
                f"删除更新文件失败，可以手动删除 {zip_path} 和 {os.path.join(target_dir, update_dir)}",
            )
